from pydantic import BaseModel

   
class MovingAveragesResponse(BaseModel):
    ticker: str
    ma_9: float
    ma_21: float
    ma_50: float
    ma_200: float
