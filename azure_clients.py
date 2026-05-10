"""
Azure service clients — lazy singletons
"""
from azure.cosmos.aio import CosmosClient
from azure.storage.blob.aio import BlobServiceClient
from azure.ai.vision.imageanalysis.aio import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.ai.textanalytics.aio import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential

from config import get_settings

settings = get_settings()

_cosmos_client = None
_blob_client = None
_vision_client = None
_language_client = None


def get_cosmos_client() -> CosmosClient:
    global _cosmos_client
    if _cosmos_client is None:
        _cosmos_client = CosmosClient(url=settings.cosmos_endpoint, credential=settings.cosmos_key)
    return _cosmos_client


def get_database():
    return get_cosmos_client().get_database_client(settings.cosmos_database)


def get_container(name: str):
    return get_database().get_container_client(name)


def get_blob_service() -> BlobServiceClient:
    global _blob_client
    if _blob_client is None:
        _blob_client = BlobServiceClient.from_connection_string(settings.storage_connection_string)
    return _blob_client


def get_blob_container():
    return get_blob_service().get_container_client(settings.storage_container)


def get_vision_client() -> ImageAnalysisClient:
    global _vision_client
    if _vision_client is None:
        _vision_client = ImageAnalysisClient(
            endpoint=settings.vision_endpoint,
            credential=AzureKeyCredential(settings.vision_key),
        )
    return _vision_client


async def analyse_image_url(blob_url: str) -> list[str]:
    try:
        client = get_vision_client()
        result = await client.analyze_from_url(
            image_url=blob_url,
            visual_features=[VisualFeatures.TAGS],
        )
        if result.tags and result.tags.list:
            return [t.name for t in result.tags.list if t.confidence >= 0.6]
    except Exception as exc:
        print(f"[Vision] Analysis failed: {exc}")
    return []


def get_language_client() -> TextAnalyticsClient:
    global _language_client
    if _language_client is None:
        _language_client = TextAnalyticsClient(
            endpoint=settings.language_endpoint,
            credential=AzureKeyCredential(settings.language_key),
        )
    return _language_client


async def analyse_sentiment(text: str) -> tuple[str, float]:
    try:
        client = get_language_client()
        docs = [{"id": "1", "text": text, "language": "en"}]
        results = await client.analyze_sentiment(docs)
        for result in results:
            if not result.is_error:
                score = max(
                    result.confidence_scores.positive,
                    result.confidence_scores.neutral,
                    result.confidence_scores.negative,
                )
                return result.sentiment, round(score, 3)
    except Exception as exc:
        print(f"[Language] Sentiment failed: {exc}")
    return "neutral", 0.5


async def close_clients():
    global _cosmos_client, _blob_client, _vision_client, _language_client
    if _cosmos_client:  await _cosmos_client.close()
    if _blob_client:    await _blob_client.close()
    if _vision_client:  await _vision_client.close()
    if _language_client: await _language_client.close()
