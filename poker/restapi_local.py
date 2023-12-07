"""Local Restapi used for React frontend"""
import io

import uvicorn
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from poker.tools.helper import COMPUTER_NAME
from poker.tools.screen_operations import take_screenshot

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://deepermind-pokerbot.com",
    ],  # Allow this origin
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)


def local_restapi():
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # You might want to be more specific in production.
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/take_screenshot")
    async def get_screenshot_result():
        screenshot = take_screenshot()
        image_bytes_io = io.BytesIO()
        screenshot.save(image_bytes_io, format="PNG")
        return Response(content=image_bytes_io.getvalue(), media_type="image/png")

    uvicorn.run(app, host="127.0.0.1", port=8005)


@app.get("/get_computer_name")
async def get_computer_name():
    return {"computer_name": COMPUTER_NAME}
