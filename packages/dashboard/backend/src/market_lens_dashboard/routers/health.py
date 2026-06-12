'''
Health-check and metadata endpoints for the dashboard backend API.
'''
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    '''
    Health-check endpoint to verify that the API is running.
    '''
    return {"status": "ok"}
