'''
Main pipeline for the Market Lens project. This module orchestrates the entire data processing workflow, including data fetching, cleaning, and feature engineering. It serves as the entry point for the pipeline, coordinating the various components and ensuring that data flows smoothly from raw sources to processed outputs ready for analysis and modeling.
'''

import argparse
import os
import json
from utils.logs import setup_logger
from .fetchers.price import fetch_historical_price_data, append_price_data
from .tickers import TICKERS as tickers
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

# Set up logging for the pipeline
logger = setup_logger()

def main():
    '''
    Main function to orchestrate the data processing pipeline.

    General Command Line Usage:
    python pipeline.py

    Command Line Arguments:
    --fetch-data: Fetch all raw data (prices and news) from sources
    --fetch-price: Fetch historical price data
    --update-price: Update price data with the latest information
    --process-data: Process price data and generate features
    '''
    argument_parser = argparse.ArgumentParser(description='Market Lens Pipeline')
    
    argument_parser.add_argument('--fetch-data', action='store_true', help='Fetch all raw data (prices and news) from sources')
    argument_parser.add_argument('--fetch-price', action='store_true', help='Fetch historical price data')
    argument_parser.add_argument('--update-price', action='store_true', help='Update price data with the latest information')
    argument_parser.add_argument('--process-data', action='store_true', help='Process price data and generate features')

    args = argument_parser.parse_args()

    # If no arguments are provided, enable full pipeline by default
    if not any([
        args.fetch_data,
        args.fetch_price,
        args.update_price,
        args.process_data
    ]):
        args.fetch_data = True
        args.process_data = True

    start_date = os.getenv("ARCHIVE_START_DATE", "2023-01-01")

    if args.fetch_data:
        # Call functions to fetch all raw data (prices and news)
        logger.info(f"Fetching all raw data for tickers...")
        pass
    elif args.fetch_price:
        # Call function to fetch historical price data
        logger.info(f"Fetching historical price data for tickers...")
        for ticker in tickers:
            fetch_historical_price_data(ticker, start_date)
    elif args.update_price:
        # Call function to update price data with the latest information
        logger.info(f"Updating price data for tickers...")
        for ticker in tickers:
            append_price_data(ticker)

    if args.process_data:
        # Call functions to process price data and generate features
        logger.info(f"Processing price data and generating features...")
        pass


if __name__ == "__main__":
    main()