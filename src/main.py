from fastapi import FastAPI

app = FastAPI(
    title="Shopify & Meta Ads Analytics",
    description="Multi-tenant analytics platform with LLM-powered weekly reports",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}
