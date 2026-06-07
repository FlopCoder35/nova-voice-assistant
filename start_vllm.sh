#!/bin/bash
# Script to serve the gpt-oss-20b model locally on JarvisLabs

echo "Starting vLLM OpenAI-compatible server for gpt-oss-20b..."
echo "Configured for MXFP4 quantization to fit within 16GB VRAM."

# Ensure vLLM is installed: pip install vllm
# We use the OpenAI-compatible entrypoint so we can use standard APIs (like aiohttp or openai package)
python3 -m vllm.entrypoints.openai.api_server \
    --model "openai/gpt-oss-20b" \
    --quantization mxfp4 \
    --tensor-parallel-size 1 \
    --max-model-len 4096 \
    --host 127.0.0.1 \
    --port 8001
