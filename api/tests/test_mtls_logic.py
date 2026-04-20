import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import Request

from app.main import get_client_identity_and_key


@pytest.mark.asyncio
async def test_identity_extraction_mock():
    # Mock the SSL object provided by Hypercorn
    mock_ssl_obj = MagicMock()

    # The new extraction logic uses binary_form=True
    def mock_getpeercert(binary_form=False):
        if binary_form:
            return b"mock_binary_cert_data"
        return {"subject": ((("commonName", "node-alpha"),),)}

    mock_ssl_obj.getpeercert.side_effect = mock_getpeercert

    mock_transport = MagicMock()
    mock_transport.get_extra_info.return_value = mock_ssl_obj

    # Create a mock FastAPI request with the ASGI scope
    scope = {"type": "http", "transport": mock_transport}
    request = Request(scope=scope)

    # Execute

    from unittest.mock import patch

    # Mock the x509 parser to return a cert with Common Name 'node-alpha'
    mock_cert = MagicMock()
    mock_cn_attr = MagicMock()
    mock_cn_attr.value = "node-alpha"
    mock_cert.subject.get_attributes_for_oid.return_value = [mock_cn_attr]
    mock_cert.public_key.return_value = MagicMock()

    with patch("cryptography.x509.load_der_x509_certificate", return_value=mock_cert):
        identity, _ = await get_client_identity_and_key(request)

    # Note: Test assertion to confirm successful extraction
    assert identity == "node-alpha"
    print(f"Identity extraction result: {identity}")


if __name__ == "__main__":
    asyncio.run(test_identity_extraction_mock())
