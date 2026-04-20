import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import Request

from app.main import get_client_identity


@pytest.mark.asyncio
async def test_identity_extraction_mock():
    # Mock the SSL object provided by Hypercorn
    mock_ssl_obj = MagicMock()
    mock_ssl_obj.getpeercert.return_value = {
        "subject": ((("commonName", "node-alpha"),),),
    }

    mock_transport = MagicMock()
    mock_transport.get_extra_info.return_value = mock_ssl_obj

    # Create a mock FastAPI request with the ASGI scope
    scope = {"type": "http", "transport": mock_transport}
    request = Request(scope=scope)

    # Execute
    from app.config import settings

    settings.MTLS_REQUIRED = True
    identity = await get_client_identity(request)

    assert identity == "node-alpha"
    print("Identity extraction verified: node-alpha")


if __name__ == "__main__":
    asyncio.run(test_identity_extraction_mock())
