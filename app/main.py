import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List

import structlog
from config import settings
from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware

# Import your workflow components
from research_workflow import (
    DeepResearchWithReflectionWorkflow,
    ProgressEvent,
    create_agents,
)
from schemas import ResearchRequest, ResearchResponse, ResearchResult, ResearchStatus

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = structlog.get_logger(__name__)

# Global storage for active research sessions
research_sessions: Dict[str, Dict[str, Any]] = {}
active_websockets: Dict[str, WebSocket] = {}

# Global agent pool (created once, reused)
agents_pool = None

# Session cleanup configuration
SESSION_TTL_HOURS = 24  # Sessions older than 24 hours will be cleaned up
CLEANUP_INTERVAL_MINUTES = 30  # Run cleanup every 30 minutes


async def cleanup_old_sessions():
    """Clean up old sessions that exceed TTL"""
    cutoff_time = datetime.now() - timedelta(hours=SESSION_TTL_HOURS)
    sessions_to_remove = []

    for session_id, session_data in research_sessions.items():
        created_at = session_data.get("created_at")
        completed_at = session_data.get("completed_at")

        # Remove if session is older than TTL
        session_age = created_at if created_at else datetime.now()
        if session_age < cutoff_time:
            sessions_to_remove.append(session_id)
        # Also remove completed sessions older than 1 hour
        elif completed_at and completed_at < (datetime.now() - timedelta(hours=1)):
            sessions_to_remove.append(session_id)

    for session_id in sessions_to_remove:
        # Cancel running task if exists
        session_data = research_sessions[session_id]
        if "task" in session_data and not session_data["task"].done():
            session_data["task"].cancel()

        # Remove from active websockets
        if session_id in active_websockets:
            del active_websockets[session_id]

        # Remove session
        del research_sessions[session_id]
        logger.info(
            "Cleaned up old session",
            component="cleanup",
            session_id=session_id,
            action="session_cleanup",
        )

    if sessions_to_remove:
        logger.info(
            "Completed session cleanup",
            component="cleanup",
            action="bulk_cleanup",
            sessions_cleaned=len(sessions_to_remove),
        )


async def periodic_cleanup():
    """Run periodic cleanup of old sessions"""
    while True:
        try:
            await cleanup_old_sessions()
        except Exception as e:
            logger.error(f"Error during session cleanup: {e}")

        # Wait for next cleanup cycle
        await asyncio.sleep(CLEANUP_INTERVAL_MINUTES * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    global agents_pool

    # Startup
    logger.info("Starting Deep Research API", component="startup")
    logger.info("Initializing agent pool", component="startup", action="agent_init")
    agents_pool = create_agents()
    logger.info(
        "Agent pool initialized successfully",
        component="startup",
        action="agent_init",
        status="success",
    )

    # Start background cleanup task
    cleanup_task = asyncio.create_task(periodic_cleanup())
    logger.info("Started periodic session cleanup task")

    yield

    # Shutdown
    logger.info("Shutting down Deep Research API")

    # Cancel cleanup task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # Cancel any running tasks
    for session_id, session_data in research_sessions.items():
        if "task" in session_data and not session_data["task"].done():
            session_data["task"].cancel()


app = FastAPI(
    title="Deep Research API",
    description="Scalable API for conducting deep research with AI agents",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware with proper configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


# Helper functions
async def run_research_workflow(
    session_id: str, topic: str, max_review_cycles: int = 3, timeout: int = 300
):
    """Run the research workflow and update session status"""
    try:
        # Update session status
        research_sessions[session_id]["status"] = "running"

        # Use pre-created agents from pool
        question_agent, answer_agent, report_agent, review_agent = agents_pool

        # Create and run workflow
        workflow = DeepResearchWithReflectionWorkflow(timeout=timeout)
        workflow.max_review_cycles = max_review_cycles

        handler = workflow.run(
            research_topic=topic,
            question_agent=question_agent,
            answer_agent=answer_agent,
            report_agent=report_agent,
            review_agent=review_agent,
        )

        # Stream events and send to WebSocket if connected
        async for ev in handler.stream_events():
            if isinstance(ev, ProgressEvent):
                progress_msg = ev.msg
                logger.info(f"Session {session_id}: {progress_msg}")

                # Update session progress
                research_sessions[session_id]["progress"] = progress_msg

                # Send to WebSocket if connected
                if session_id in active_websockets:
                    try:
                        await active_websockets[session_id].send_json(
                            {
                                "type": "progress",
                                "session_id": session_id,
                                "message": progress_msg,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send WebSocket message: {e}")

        # Get final result
        final_result = await handler

        # Update session with result
        research_sessions[session_id].update(
            {
                "status": "completed",
                "result": final_result,
                "completed_at": datetime.now(),
                "review_cycles": workflow.review_cycles,
            }
        )

        # Send completion message to WebSocket
        if session_id in active_websockets:
            try:
                await active_websockets[session_id].send_json(
                    {
                        "type": "completed",
                        "session_id": session_id,
                        "result": final_result,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to send completion WebSocket message: {e}")

        logger.info(
            "Research workflow completed",
            component="research",
            action="complete_session",
            session_id=session_id,
            review_cycles=workflow.review_cycles,
        )

    except Exception as e:
        error_msg = str(e)
        # Categorize error types for better handling
        if "timeout" in error_msg.lower():
            status = "timeout"
        elif "cancel" in error_msg.lower():
            status = "cancelled"
        else:
            status = "failed"

        logger.error(f"Error in research workflow {session_id}: {error_msg}")

        # Update session with categorized error
        research_sessions[session_id].update(
            {"status": status, "error": error_msg, "completed_at": datetime.now()}
        )

        # Send error to WebSocket
        if session_id in active_websockets:
            try:
                await active_websockets[session_id].send_json(
                    {
                        "type": "error",
                        "session_id": session_id,
                        "error": error_msg,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to send error WebSocket message: {e}")


# API endpoints
@app.post("/research/start", response_model=ResearchResponse)
async def start_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    """Start a new research session"""
    session_id = str(uuid.uuid4())

    # Initialize session
    research_sessions[session_id] = {
        "session_id": session_id,
        "topic": request.topic,
        "status": "initializing",
        "created_at": datetime.now(),
        "progress": None,
        "result": None,
        "error": None,
        "review_cycles": 0,
    }

    # Start background task and store reference
    task = asyncio.create_task(
        run_research_workflow(
            session_id, request.topic, request.max_review_cycles, request.timeout
        )
    )
    research_sessions[session_id]["task"] = task

    logger.info(
        "Research session started",
        component="research",
        action="start_session",
        session_id=session_id,
        topic=request.topic[:50] + "..." if len(request.topic) > 50 else request.topic,
    )

    return ResearchResponse(
        session_id=session_id,
        status="started",
        message=f"Research session started for topic: {request.topic}",
    )


@app.get("/research/{session_id}/status", response_model=ResearchStatus)
async def get_research_status(session_id: str):
    """Get the status of a research session"""
    if session_id not in research_sessions:
        raise HTTPException(status_code=404, detail="Research session not found")

    session_data = research_sessions[session_id]
    return ResearchStatus(**session_data)


@app.get("/research/{session_id}/result", response_model=ResearchResult)
async def get_research_result(session_id: str):
    """Get the result of a completed research session"""
    if session_id not in research_sessions:
        raise HTTPException(status_code=404, detail="Research session not found")

    session_data = research_sessions[session_id]

    if session_data["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Research session is not completed. Current status: {session_data['status']}",
        )

    return ResearchResult(
        session_id=session_id,
        topic=session_data["topic"],
        report=session_data["result"],
        completed_at=session_data["completed_at"],
        review_cycles=session_data["review_cycles"],
    )


@app.get("/research/sessions", response_model=List[ResearchStatus])
async def list_research_sessions():
    """List all research sessions"""
    return [
        ResearchStatus(**session_data) for session_data in research_sessions.values()
    ]


@app.delete("/research/{session_id}")
async def cancel_research_session(session_id: str):
    """Cancel a research session"""
    if session_id not in research_sessions:
        raise HTTPException(status_code=404, detail="Research session not found")

    session_data = research_sessions[session_id]

    # Cancel the task if it's running
    if "task" in session_data and not session_data["task"].done():
        session_data["task"].cancel()
        session_data["status"] = "cancelled"
        session_data["completed_at"] = datetime.now()

        # Notify via WebSocket if connected
        if session_id in active_websockets:
            try:
                await active_websockets[session_id].send_json(
                    {
                        "type": "cancelled",
                        "session_id": session_id,
                        "message": "Research session cancelled",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to send cancellation WebSocket message: {e}")

        logger.info(f"Cancelled research session {session_id}")
        return {"message": f"Research session {session_id} cancelled"}
    else:
        return {
            "message": f"Research session {session_id} was not running or already completed"
        }


@app.websocket("/research/{session_id}/ws")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time progress updates"""
    try:
        await websocket.accept()
        active_websockets[session_id] = websocket
        logger.info(f"WebSocket connected for session {session_id}")

        # Send initial status if session exists
        if session_id in research_sessions:
            session_data = research_sessions[session_id]
            await websocket.send_json(
                {
                    "type": "status",
                    "session_id": session_id,
                    "status": session_data["status"],
                    "timestamp": datetime.now().isoformat(),
                }
            )
        else:
            # Send error if session doesn't exist
            await websocket.send_json(
                {
                    "type": "error",
                    "session_id": session_id,
                    "error": "Session not found",
                    "timestamp": datetime.now().isoformat(),
                }
            )
            return

        # Keep connection alive
        while True:
            try:
                # Wait for any message (ping/pong) with shorter timeout
                data = await asyncio.wait_for(websocket.receive_text(), timeout=20.0)

                # Handle client messages if needed (e.g., pong responses)
                if data == "pong":
                    logger.debug(f"Received pong from session {session_id}")

            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                try:
                    await websocket.send_json(
                        {"type": "ping", "timestamp": datetime.now().isoformat()}
                    )
                except Exception as ping_error:
                    logger.warning(
                        f"Failed to send ping to session {session_id}: {ping_error}"
                    )
                    break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        try:
            # Try to send error message before closing
            await websocket.send_json(
                {
                    "type": "error",
                    "session_id": session_id,
                    "error": f"Connection error: {str(e)}",
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except Exception:
            pass  # Connection might already be closed
    finally:
        # Always clean up websocket reference
        if session_id in active_websockets:
            del active_websockets[session_id]
            logger.info(f"Cleaned up WebSocket for session {session_id}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(research_sessions),
        "active_websockets": len(active_websockets),
    }


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Deep Research API",
        "version": "1.0.0",
        "description": "Scalable API for conducting deep research with AI agents",
        "endpoints": {
            "start_research": "POST /research/start",
            "get_status": "GET /research/{session_id}/status",
            "get_result": "GET /research/{session_id}/result",
            "list_sessions": "GET /research/sessions",
            "cancel_session": "DELETE /research/{session_id}",
            "websocket": "WS /research/{session_id}/ws",
            "health": "GET /health",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
