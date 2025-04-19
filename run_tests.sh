# run_tests.sh
#!/bin/bash

# Set environment variables for testing
export TESTING=1
export REDIS_URL="redis://localhost:6379/1"
export DB_HOST="localhost"
export TELEGRAM_TOKEN="test_token"
export VIBER_TOKEN="test_token"
export TWILIO_ACCOUNT_SID="test_sid"
export TWILIO_AUTH_TOKEN="test_token"
export TWILIO_PHONE_NUMBER="whatsapp:+1234567890"

# Install test dependencies
pip install -r requirements-test.txt

# Run tests with coverage
pytest --cov=services --cov=common --cov-report=term --cov-report=html:coverage_html tests/

# Optional: Run only unit tests (excluding integration tests)
# pytest -m "not integration" --cov=services --cov=common --cov-report=term tests/