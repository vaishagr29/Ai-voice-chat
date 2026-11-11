
import asyncio
import os
import tempfile
import time
import wave

import httpx

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from faster_whisper import WhisperModel
from piper import PiperVoice

from database import (
    create_table,
    save_message,
    get_history,
    delete_history,
    get_all_sessions
)


app = FastAPI(
    title="Realtime AI Voice Chat",
    description="A real-time AI voice assistant",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

create_table()


# System prompt
SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "You are a helpful AI voice assistant. "
        "Give short, simple and clear answers by default. "
        "Use 1-3 sentences unless the user asks for more details. "
        "If the user asks for a one-line answer, reply in exactly one line. "
        "Avoid unnecessary headings, lists and repetition. "
        "Use simple English and sound natural when spoken aloud."
    )
}


# Load Whisper model once
print("Loading Whisper model...")

whisper_model = WhisperModel(
    "tiny",
    device="cpu",
    compute_type="int8"
)

print("Whisper model loaded!")


# Load Piper voice once
print("Loading Piper voice...")

piper_voice = PiperVoice.load(
    "models/piper/en_US-lessac-medium.onnx"
)

print("Piper voice loaded!")


# Locks prevent overlapping use of the local models
whisper_lock = asyncio.Lock()
piper_lock = asyncio.Lock()


# Convert text into speech
def generate_speech(text):

    temp_audio = tempfile.NamedTemporaryFile(
        suffix=".wav",
        delete=False
    )

    try:
        with wave.open(temp_audio.name, "wb") as wav_file:
            piper_voice.synthesize_wav(text, wav_file)

        return temp_audio.name

    except Exception:
        if os.path.exists(temp_audio.name):
            os.remove(temp_audio.name)
        raise

    finally:
        temp_audio.close()


# Convert recorded audio into text
def transcribe_audio(audio_bytes):

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".webm",
            delete=False
        ) as temp_audio:

            temp_audio.write(audio_bytes)
            temp_path = temp_audio.name

        start_time = time.perf_counter()

        segments, info = whisper_model.transcribe(
            temp_path,
            beam_size=1,
            vad_filter=True
        )

        transcript = " ".join(
            segment.text.strip() for segment in segments
        ).strip()

        end_time = time.perf_counter()

        print(
            f"Whisper processing time: "
            f"{end_time - start_time:.2f} seconds"
        )

        return transcript

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# Run blocking work safely in a background thread.
# If the turn is cancelled, wait for the thread to finish
# before allowing another call to use the same model.
async def run_thread_safely(function, *args):

    worker = asyncio.create_task(
        run_in_threadpool(function, *args)
    )

    try:
        return await asyncio.shield(worker)

    except asyncio.CancelledError:

        result = None

        try:
            result = await worker
        except Exception:
            pass

        # Remove a generated audio file if its turn was cancelled
        if isinstance(result, str) and os.path.exists(result):
            os.remove(result)

        raise


@app.get("/")
def home():
    return {
        "message": "Realtime AI Voice Chat is running!"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.get("/history")
def chat_history():
    return get_all_sessions()


@app.get("/history/{session_id}")
def get_chat_messages(session_id: str):
    return get_history(session_id)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    await websocket.accept()

    print("Client connected!")

    session_id = websocket.query_params.get("session_id")

    if not session_id:
        await websocket.close(code=1008)
        return

    # Load previous conversation
    conversation = [
        SYSTEM_PROMPT.copy()
    ]

    conversation.extend(get_history(session_id))

    print(
        "Conversation history loaded:",
        len(conversation) - 1,
        "messages"
    )

    # Track the currently active AI turn
    current_turn_id = 0
    active_task = None

    def cancel_active_turn():

        nonlocal current_turn_id, active_task

        # Every new turn gets a new ID
        current_turn_id += 1

        # Cancel the previous AI task
        if active_task and not active_task.done():
            active_task.cancel()
            print("Previous AI turn cancelled!")

        active_task = None

        return current_turn_id

    async def process_turn(
        turn_id,
        user_message,
        turn_start
    ):

        nonlocal conversation

        audio_path = None

        try:

            # Process voice input
            if isinstance(user_message, bytes):

                print("Audio received!")

                async with whisper_lock:

                    user_text = await run_thread_safely(
                        transcribe_audio,
                        user_message
                    )

                if turn_id != current_turn_id:
                    return

                if not user_text:

                    await websocket.send_text(
                        "Sorry, I couldn't understand that. Please try again."
                    )

                    return

                print("Whisper transcript:", user_text)

            else:

                user_text = user_message

                print("Received:", user_text)

            # Check whether this is still the latest turn
            if turn_id != current_turn_id:
                return

            # Save user message
            save_message(
                session_id,
                "user",
                user_text
            )

            conversation.append({
                "role": "user",
                "content": user_text
            })

            # Make a snapshot of the conversation
            # so another turn cannot change this request's messages
            messages_for_ai = [
                item.copy() for item in conversation
            ]

            # Send conversation to Ollama
            ollama_start = time.perf_counter()

            try:

                async with httpx.AsyncClient() as client:

                    response = await client.post(
                        f"{os.getenv('OLLAMA_HOST', 'http://localhost:11434')}/api/chat",
                        json={
                            "model": "llama3.2:1b",
                            "messages": messages_for_ai,
                            "stream": False
                        },
                        timeout=120.0
                    )

                    response.raise_for_status()

                    ai_reply = response.json()["message"]["content"]

                ollama_end = time.perf_counter()

                print(
                    f"Ollama response time: "
                    f"{ollama_end - ollama_start:.2f} seconds"
                )

            except httpx.TimeoutException:

                if turn_id == current_turn_id:
                    await websocket.send_text(
                        "Ollama is taking too long to respond. Please try again."
                    )

                return

            except httpx.HTTPStatusError:

                if turn_id == current_turn_id:
                    await websocket.send_text(
                        "Ollama returned an error. Please try again."
                    )

                return

            except httpx.RequestError:

                if turn_id == current_turn_id:
                    await websocket.send_text(
                        "Cannot connect to Ollama. Please check if Ollama is running."
                    )

                return

            # Do not use an outdated AI response
            if turn_id != current_turn_id:
                return

            print("AI:", ai_reply)

            # Save the latest AI response
            save_message(
                session_id,
                "assistant",
                ai_reply
            )

            conversation.append({
                "role": "assistant",
                "content": ai_reply
            })

            await websocket.send_text(ai_reply)

            # Generate speech using Piper
            piper_start = time.perf_counter()

            async with piper_lock:

                audio_path = await run_thread_safely(
                    generate_speech,
                    ai_reply
                )

            piper_end = time.perf_counter()

            print(
                f"Piper processing time: "
                f"{piper_end - piper_start:.2f} seconds"
            )

            # Check again before sending audio
            if turn_id != current_turn_id:
                return

            with open(audio_path, "rb") as audio_file:
                audio_bytes = audio_file.read()

            await websocket.send_bytes(audio_bytes)

            turn_end = time.perf_counter()

            print(
                f"Total backend response time: "
                f"{turn_end - turn_start:.2f} seconds"
            )

        except asyncio.CancelledError:

            print(f"Turn {turn_id} interrupted!")

            raise

        except WebSocketDisconnect:

            print("WebSocket disconnected during AI processing!")

        except Exception as e:

            print("AI processing error:", e)

            if turn_id == current_turn_id:

                try:
                    await websocket.send_text(
                        "Sorry, something went wrong with the AI."
                    )
                except Exception:
                    pass

        finally:

            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)

    try:

        while True:

            # Keep receiving messages even while AI is processing
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            # Handle manual interruption command
            if message.get("text") == "__INTERRUPT__":

                cancel_active_turn()

                print("AI interrupted by user!")

                continue

            # Handle clear chat
            if message.get("text") == "__CLEAR_CHAT__":

                cancel_active_turn()

                delete_history(session_id)

                conversation = [
                    SYSTEM_PROMPT.copy()
                ]

                await websocket.send_text("__CHAT_CLEARED__")

                continue

            # Receive a new voice or text message
            if message.get("bytes") is not None:

                user_message = message["bytes"]

            elif message.get("text") is not None:

                user_message = message["text"]

            else:

                continue

            # A new message interrupts the previous turn
            turn_id = cancel_active_turn()

            turn_start = time.perf_counter()

            # Start processing without blocking the receiver
            active_task = asyncio.create_task(
                process_turn(
                    turn_id,
                    user_message,
                    turn_start
                )
            )

    except WebSocketDisconnect:

        print("Client disconnected!")

    except Exception as e:

        print("WebSocket error:", e)

    finally:

        cancel_active_turn()

        if active_task:

            await asyncio.gather(
                active_task,
                return_exceptions=True
            )

        print("WebSocket connection closed!")
