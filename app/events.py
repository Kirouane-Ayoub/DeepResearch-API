from llama_index.core.workflow import Event


class FeedbackEvent(Event):
    feedback: str
    research_topic: str


class ReviewEvent(Event):
    report: str


class SecondEvent(Event):
    second_output: str
    response: str


class TextEvent(Event):
    delta: str


class FirstEvent(Event):
    first_output: str


class StepAEvent(Event):
    query: str


class StepACompleteEvent(Event):
    result: str


class StepBEvent(Event):
    query: str


class StepBCompleteEvent(Event):
    result: str


class StepCEvent(Event):
    query: str


class StepCCompleteEvent(Event):
    result: str


class GenerateEvent(Event):
    research_topic: str


class AnswerEvent(Event):
    question: str
    answer: str


class ProgressEvent(Event):
    msg: str


class QuestionEvent(Event):
    question: str
