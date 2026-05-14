#!/usr/bin/env python3
"""
Simple test for Vibe-Trading API with grok-4-1-fast-reasoning model
"""
import requests
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)

def test_vibe_api():
    """Test Vibe-Trading API with a simple prompt"""
    url = "http://localhost:8899/swarm/runs"
    payload = {
        "preset_name": "crypto_trading_desk",
        "user_vars": {
            "target": "ETH-USDT",
            "timeframe": "swing 1-2 weeks"
        }
    }

    logger.info("Testing Vibe-Trading API with grok-4-1-fast-reasoning model")
    logger.info(f"Sending request to {url}")
    logger.info(f"Payload: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        logger.info(f"Run create response: {json.dumps(result, ensure_ascii=False)}")
        run_id = result.get('id') or result.get('run_id')
        if not run_id:
            logger.error('Run response did not include run id')
            return False

        logger.info(f"Started run: {run_id}")

        # Poll for completion
        max_polls = 360  # 30 minutes max
        for i in range(max_polls):
            status_url = f"http://localhost:8899/swarm/runs/{run_id}"
            status_response = requests.get(status_url, timeout=10)
            status_response.raise_for_status()
            status_data = status_response.json()

            status = status_data.get('status')
            if status is None:
                logger.warning(f"Run status field missing; response keys: {list(status_data.keys())}")
            logger.info(f"Run status: {status} (poll {i+1}/{max_polls})")

            if status == 'completed':
                logger.info("Run completed successfully!")
                final_report = status_data.get('final_report')
                if final_report:
                    logger.info("Final report received")
                    print(json.dumps(final_report, indent=2, ensure_ascii=False))
                else:
                    logger.warning("Run completed but no final_report field available")
                    print(json.dumps(status_data, indent=2, ensure_ascii=False))
                return True
            elif status in ('failed', 'timeout', 'cancelled'):
                logger.error(f"Run ended with status: {status}")
                if status_data.get('final_report'):
                    print(json.dumps(status_data['final_report'], indent=2, ensure_ascii=False))
                return False

            time.sleep(5)

        logger.error(f"Run timed out after {max_polls * 5 / 60:.0f} minutes")
        return False

    except Exception as e:
        logger.error(f"API test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_vibe_api()
    print(f"\nTest result: {'SUCCESS' if success else 'FAILED'}")