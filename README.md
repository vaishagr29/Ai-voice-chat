# Realtime AI Voice Chat Assistant

I built this project to explore how voice-based AI assistants work. It allows users to chat with an AI assistant using either text or their voice.

When a user speaks, the application converts their speech into text, gets a response from a locally running AI model, and converts that response into speech.

I also worked on containerizing the backend using Docker.

## What it can do

- Chat with the assistant using text or voice.
- Convert speech into text using Whisper.
- Generate responses using Ollama and Llama 3.2 (1B).
- Convert AI responses into speech using Piper TTS.
- Communicate between the frontend and backend using WebSockets.
- Save chat history using SQLite.
- Start a new chat or clear an existing conversation.

## Technologies I used

- **Python and FastAPI** – Backend and API development.
- **WebSockets** – Real-time communication.
- **Faster-Whisper** – Speech recognition.
- **Ollama (Llama 3.2 1B)** – Generating AI responses locally.
- **Piper TTS** – Converting text into speech.
- **SQLite** – Storing chat history.
- **HTML, CSS and JavaScript** – Frontend.
- **Docker and Docker Compose** – Building and running the backend in a container.

## How it works

1. The user enters a message or speaks through the microphone.
2. If it's a voice message, Whisper converts it into text.
3. The backend sends the message to Ollama.
4. Ollama generates a response using the local language model.
5. Piper converts the response into audio.
6. The response is sent back to the browser, where the user can read or listen to it.

## Getting started

### Requirements

- Docker
- Docker Compose
- Ollama installed on your machine
- Llama 3.2 1B model

### 1. Clone the repository

```bash
git clone https://github.com/vaishagr29/Ai-voice-chat.git
cd Ai-voice-chat
```

### 2. Set up Ollama

Install Ollama from [ollama.com](https://ollama.com/).

Download the model:

```bash
ollama pull llama3.2:1b
```

Make sure Ollama is running on your machine.

### 3. Build and run the backend

```bash
docker-compose up --build -d
```

Docker builds the backend image, installs the required packages, and downloads the Piper voice model during the build.

### 4. Open the frontend

```bash
open frontend/index.html
```

The frontend opens in your browser. The backend runs separately in Docker.

### 5. Check if the backend is running

Open this URL in your browser:

`http://localhost:8000/health`

You should see:

```json
{"status": "healthy"}
```

## Useful Docker commands

```bash
# Check running containers
docker-compose ps

# View backend logs
docker-compose logs -f backend

# Stop the containers
docker-compose down
```

## A little about the Docker setup

I used Docker to package the backend and its dependencies so it can run in a consistent environment.

The Piper voice model is a large file, so I decided not to upload it to GitHub. Instead, the Dockerfile downloads it while building the image. This keeps the Git repository smaller.

## What's next?

I plan to explore Kubernetes and use it to manage the application's containers.

## Author

**Vaishnavi Agrawal**