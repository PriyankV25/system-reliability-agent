@echo off
setlocal
echo Make sure Ollama is installed and running locally.
echo Pulling Gemma 3 4B...
ollama pull gemma3:4b
echo.
echo Model is ready. The application uses http://127.0.0.1:11434
pause
