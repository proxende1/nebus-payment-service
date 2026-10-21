from fastapi import FastAPI, Request
import uvicorn
from fastapi.responses import JSONResponse

app = FastAPI()


@app.post("/webhook")
async def receive_webhook(request: Request):
    data = await request.json()

    print("Webhook received!")
    print("Payload:", data)


    return {"received": True}



if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
