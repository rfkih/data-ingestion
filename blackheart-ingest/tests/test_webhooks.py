import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from blackheart_ingest.webhooks import notify_inference_batch_ready


@pytest.mark.asyncio
async def test_notify_inference_batch_ready_success():
    """Test webhook call succeeds and returns response."""
    with patch('blackheart_ingest.webhooks.httpx.AsyncClient') as mock_client_cls:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        # response.json() is synchronous in httpx, not async
        mock_response.json = MagicMock(return_value={"status": "ok", "queued": 8})
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await notify_inference_batch_ready(
            base_url="http://127.0.0.1:8000",
            auth_token="dev-token",
            compute_run_id="test-run-123"
        )

        assert result["status"] == "ok"
        assert result["queued"] == 8
        mock_client.post.assert_called_once()
        mock_response.raise_for_status.assert_called_once()


@pytest.mark.asyncio
async def test_notify_inference_batch_ready_http_error():
    """Test that HTTP errors are propagated correctly."""
    with patch('blackheart_ingest.webhooks.httpx.AsyncClient') as mock_client_cls:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        # raise_for_status() is synchronous in httpx
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "500 Server Error",
                request=MagicMock(),
                response=mock_response,
            )
        )
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Should raise HTTPStatusError
        with pytest.raises(httpx.HTTPStatusError):
            await notify_inference_batch_ready(
                base_url="http://127.0.0.1:8000",
                auth_token="dev-token",
                compute_run_id="test-run-123"
            )
