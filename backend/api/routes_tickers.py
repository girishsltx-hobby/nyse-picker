"""REST endpoints for managing tickers in config.py"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()

# Path to config.py
CONFIG_PATH = Path(__file__).parent.parent / "config.py"


def _read_tickers() -> list[str]:
    """Read TICKERS list from config.py"""
    try:
        content = CONFIG_PATH.read_text()
        match = re.search(r'TICKERS\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if not match:
            logger.error("Could not find TICKERS definition in config.py")
            return []
        tickers_str = match.group(1)
        tickers = [t.strip().strip('"\'') for t in tickers_str.split(',') if t.strip()]
        return tickers
    except Exception as e:
        logger.error("Error reading TICKERS from config.py: %s", e)
        return []


def _write_tickers(tickers: list[str]) -> None:
    """Write TICKERS list to config.py"""
    try:
        content = CONFIG_PATH.read_text()
        tickers_formatted = ', '.join(f'"{t}"' for t in tickers)
        new_content = re.sub(
            r'TICKERS\s*=\s*\[.*?\]',
            f'TICKERS = [{tickers_formatted}]',
            content,
            flags=re.DOTALL
        )
        CONFIG_PATH.write_text(new_content)
        logger.info("Updated TICKERS in config.py: %s", tickers)
    except Exception as e:
        logger.error("Error writing TICKERS to config.py: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to update config.py: {e}")


@router.get("/tickers")
async def get_tickers():
    """Get current list of tickers from config.py"""
    tickers = _read_tickers()
    return {"tickers": tickers}


@router.post("/tickers/add")
async def add_ticker(ticker: str):
    """Add a ticker to config.py (without fetching data - that happens in refresh)"""
    ticker = ticker.strip().upper()
    if not ticker or not re.match(r'^[A-Z0-9]{1,5}$', ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format")
    
    tickers = _read_tickers()
    if ticker in tickers:
        raise HTTPException(status_code=400, detail=f"Ticker {ticker} already exists")
    
    tickers.append(ticker)
    _write_tickers(tickers)
    logger.info(f"Added ticker {ticker} to config")
    return {"status": "ok", "tickers": tickers}


@router.post("/tickers/remove")
async def remove_ticker(ticker: str):
    """Remove a ticker from config.py"""
    ticker = ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    
    tickers = _read_tickers()
    if ticker not in tickers:
        raise HTTPException(status_code=400, detail=f"Ticker {ticker} not found")
    
    tickers.remove(ticker)
    _write_tickers(tickers)
    return {"status": "ok", "tickers": tickers}
