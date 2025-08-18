import asyncio

from config import settings
from dotenv import load_dotenv
from events import (
    AnswerEvent,
    FeedbackEvent,
    GenerateEvent,
    ProgressEvent,
    QuestionEvent,
    ReviewEvent,
)
from google import genai
from google.genai import types
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.workflow import (
    Context,
    StartEvent,
    StopEvent,
    Workflow,
    step,
)
from llama_index.llms.google_genai import GoogleGenAI

# Load environment variables from .env file
load_dotenv(override=True)

llm = GoogleGenAI(model="gemini-2.5-flash")


def search_web(query: str, max_retries: int = 3):
    """Web search function using Google's Genai API with retry logic"""
    query = f"Search for : {query}"

    for attempt in range(max_retries):
        try:
            client = genai.Client(
                api_key=settings.GEMINI_API_KEY,
            )

            model = "gemini-2.5-flash-lite"
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=query),
                    ],
                ),
            ]
            tools = [
                types.Tool(googleSearch=types.GoogleSearch()),
            ]
            generate_content_config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_budget=-1,
                ),
                tools=tools,
            )

            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=generate_content_config,
            )
            return response.text

        except Exception as e:
            if attempt == max_retries - 1:  # Last attempt
                error_msg = f"Web search failed after {max_retries} attempts: {str(e)}"
                print(f"ERROR: {error_msg}")
                return f"Unable to search web: {error_msg}"
            else:
                print(f"Web search attempt {attempt + 1} failed: {str(e)}. Retrying...")
                continue


def create_agents():
    """Factory function to create all required agents"""
    question_agent = FunctionAgent(
        tools=[],
        llm=llm,
        verbose=False,
        system_prompt="""You are part of a deep research system.
          Given a research topic, you should come up with 5 questions
          that a separate agent will answer in order to write a comprehensive
          report on that topic. To make it easy to answer the questions separately,
          you should provide the questions one per line. Don't include markdown
          or any preamble in your response, just a list of questions.""",
    )

    answer_agent = FunctionAgent(
        tools=[search_web],
        llm=llm,
        verbose=False,
        system_prompt="""You are part of a deep research system.
          Given a specific question, your job is to come up with a deep answer
          to that question, which will be combined with other answers on the topic
          into a comprehensive report. You can search the web to get information
          on the topic, as many times as you need.""",
    )

    report_agent = FunctionAgent(
        tools=[],
        llm=llm,
        verbose=False,
        system_prompt="""You are part of a deep research system.
          Given a set of answers to a set of questions, your job is to combine
          them all into a comprehensive report on the topic.""",
    )

    review_agent = FunctionAgent(
        tools=[],
        llm=llm,
        verbose=False,
        system_prompt="""You are part of a deep research system.
          Your job is to review a report that's been written and suggest
          questions that could have been asked to produce a more comprehensive
          report than the current version, or to decide that the current
          report is comprehensive enough.""",
    )

    return question_agent, answer_agent, report_agent, review_agent


class DeepResearchWithReflectionWorkflow(Workflow):
    def __init__(self, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.review_cycles = 0
        self.max_review_cycles = 3

    @step
    async def setup(self, ctx: Context, ev: StartEvent) -> GenerateEvent:
        self.question_agent = ev.question_agent
        self.answer_agent = ev.answer_agent
        self.report_agent = ev.report_agent
        self.review_agent = ev.review_agent
        self.review_cycles = 0

        ctx.write_event_to_stream(ProgressEvent(msg="Starting research"))

        return GenerateEvent(research_topic=ev.research_topic)

    @step
    async def generate_questions(
        self, ctx: Context, ev: GenerateEvent | FeedbackEvent
    ) -> QuestionEvent:

        await ctx.set("research_topic", ev.research_topic)
        ctx.write_event_to_stream(
            ProgressEvent(msg=f"Research topic is {ev.research_topic}")
        )

        prompt = f"""Generate some questions on the topic <topic>{ev.research_topic}</topic>."""

        if isinstance(ev, FeedbackEvent):
            ctx.write_event_to_stream(ProgressEvent(msg=f"Got feedback: {ev.feedback}"))
            prompt += f"""You have previously researched this topic and
                got the following feedback, consisting of additional questions
                you might want to ask: <feedback>{ev.feedback}</feedback>.
                Keep this in mind when formulating your questions."""

        result = await self.question_agent.run(user_msg=prompt)

        # some basic string manipulation to get separate questions
        lines = str(result).split("\n")
        questions = [line.strip() for line in lines if line.strip() != ""]

        # record how many answers we're going to need to wait for
        await ctx.set("total_questions", len(questions))

        # fire off multiple Answer Agents
        for question in questions:
            ctx.send_event(QuestionEvent(question=question))

    @step
    async def answer_question(self, ctx: Context, ev: QuestionEvent) -> AnswerEvent:
        """Answer a question with timeout and error handling"""
        try:
            # Add timeout for individual question processing
            result = await asyncio.wait_for(
                self.answer_agent.run(
                    user_msg=f"""Research the answer to this
                  question: <question>{ev.question}</question>. You can use web
                  search to help you find information on the topic, as many times
                  as you need. Return just the answer without preamble or markdown.""",
                    max_iterations=5,
                ),
                timeout=120,  # 2 minute timeout per question
            )

            ctx.write_event_to_stream(
                ProgressEvent(
                    msg=f"""Completed question: {ev.question[:50]}...
                Answer: {str(result)[:100]}..."""
                )
            )

            return AnswerEvent(question=ev.question, answer=str(result))

        except asyncio.TimeoutError:
            error_answer = "Timeout occurred while researching this question. Unable to complete research within 2 minutes."
            ctx.write_event_to_stream(
                ProgressEvent(msg=f"Timeout for question: {ev.question[:50]}...")
            )
            return AnswerEvent(question=ev.question, answer=error_answer)

        except Exception as e:
            error_answer = f"Error occurred while researching this question: {str(e)}"
            ctx.write_event_to_stream(
                ProgressEvent(
                    msg=f"Error for question: {ev.question[:50]}... - {str(e)}"
                )
            )
            return AnswerEvent(question=ev.question, answer=error_answer)

    @step
    async def write_report(self, ctx: Context, ev: AnswerEvent) -> ReviewEvent:

        research = ctx.collect_events(
            ev, [AnswerEvent] * await ctx.get("total_questions")
        )
        # if we haven't received all the answers yet, this will be None
        if research is None:
            ctx.write_event_to_stream(ProgressEvent(msg="Collecting answers..."))
            return None

        ctx.write_event_to_stream(ProgressEvent(msg="Generating report..."))

        # aggregate the questions and answers
        all_answers = ""
        for q_and_a in research:
            all_answers += f"Question: {q_and_a.question}\nAnswer: {q_and_a.answer}\n\n"

        # prompt the report
        result = await self.report_agent.run(
            user_msg=f"""You are part of a deep research system.
          You have been given a complex topic on which to write a report:
          <topic>{await ctx.store.get("research_topic")}</topic>.

          Other agents have already come up with a list of questions about the
          topic and answers to those questions. Your job is to write a clear,
          thorough report that combines all the information from those answers.

          Here are the questions and answers:
          <questions_and_answers>{all_answers}</questions_and_answers>"""
        )

        return ReviewEvent(report=str(result))

    @step
    async def review(self, ctx: Context, ev: ReviewEvent) -> StopEvent | FeedbackEvent:

        result = await self.review_agent.run(
            user_msg=f"""You are part of a deep research system.
          You have just written a report about the topic {await ctx.store.get("research_topic")}.
          Here is the report: <report>{ev.report}</report>
          Decide whether this report is sufficiently comprehensive.
          If it is, respond with just the string "ACCEPTABLE" and nothing else.
          If it needs more research, suggest some additional questions that could
          have been asked."""
        )

        self.review_cycles += 1

        # either it's okay or we've already gone through max cycles
        if str(result) == "ACCEPTABLE" or self.review_cycles >= self.max_review_cycles:
            return StopEvent(result=ev.report)
        else:
            ctx.write_event_to_stream(ProgressEvent(msg="Sending feedback"))
            return FeedbackEvent(
                research_topic=await ctx.store.get("research_topic"),
                feedback=str(result),
            )
