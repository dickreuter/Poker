"""Local Restapi used for React frontend"""
import io

import uvicorn
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from poker.tools.screen_operations import take_screenshot

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173",
                   "http://deepermind-pokerbot.com"],  # Allow this origin
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)


def local_restapi():

    @app.get("/take_screenshot")
    async def get_screenshot_result():
        screenshot = take_screenshot()
        image_bytes_io = io.BytesIO()
        screenshot.save(image_bytes_io, format="PNG")
        return Response(content=image_bytes_io.getvalue(), media_type="image/png")

    uvicorn.run(app, host="0.0.0.0", port=8005)
