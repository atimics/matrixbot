#!/usr/bin/env python3
"""
Unit tests for the get_relevant_fungible_owners method in NeynarAPIClient
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient


class TestGetRelevantFungibleOwners:
    """Test cases for get_relevant_fungible_owners method"""

    @pytest.fixture
    def mock_client(self):
        """Create a NeynarAPIClient with mocked HTTP client"""
        client = NeynarAPIClient(api_key="test_key")
        client._make_request = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_relevant_fungible_owners_success(self, mock_client):
        """Test successful retrieval of relevant fungible owners"""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "top_relevant_fungible_owners_hydrated": [
                {
                    "object": "user",
                    "fid": 3,
                    "username": "dan",
                    "display_name": "Dan Romero",
                    "custody_address": "0x5a927ac639636e534b678e81768ca19e2c6280b7",
                    "pfp_url": "https://example.com/pfp.jpg"
                }
            ],
            "all_relevant_fungible_owners_dehydrated": [
                {
                    "object": "user",
                    "fid": 3,
                    "username": "dan"
                },
                {
                    "object": "user", 
                    "fid": 5,
                    "username": "vitalik"
                }
            ]
        }
        mock_client._make_request.return_value = mock_response

        # Test the method
        result = await mock_client.get_relevant_fungible_owners(
            contract_address="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
            network="base",
            viewer_fid=3
        )

        # Verify the request was made correctly
        mock_client._make_request.assert_called_once_with(
            "GET",
            "/farcaster/fungible/owner/relevant",
            params={
                "contract_address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
                "network": "base",
                "viewer_fid": 3
            }
        )

        # Verify the response
        assert result is not None
        assert "top_relevant_fungible_owners_hydrated" in result
        assert "all_relevant_fungible_owners_dehydrated" in result
        assert len(result["top_relevant_fungible_owners_hydrated"]) == 1
        assert len(result["all_relevant_fungible_owners_dehydrated"]) == 2
        assert result["top_relevant_fungible_owners_hydrated"][0]["username"] == "dan"

    @pytest.mark.asyncio
    async def test_get_relevant_fungible_owners_without_viewer_fid(self, mock_client):
        """Test successful request without viewer_fid parameter"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "top_relevant_fungible_owners_hydrated": [],
            "all_relevant_fungible_owners_dehydrated": []
        }
        mock_client._make_request.return_value = mock_response

        result = await mock_client.get_relevant_fungible_owners(
            contract_address="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
            network="ethereum"
        )

        # Verify the request was made without viewer_fid
        mock_client._make_request.assert_called_once_with(
            "GET",
            "/farcaster/fungible/owner/relevant",
            params={
                "contract_address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
                "network": "ethereum"
            }
        )

        assert result is not None
        assert "top_relevant_fungible_owners_hydrated" in result
        assert "all_relevant_fungible_owners_dehydrated" in result

    @pytest.mark.asyncio 
    async def test_get_relevant_fungible_owners_invalid_contract_address(self, mock_client):
        """Test with empty contract address"""
        with pytest.raises(ValueError, match="contract_address is required and cannot be empty"):
            await mock_client.get_relevant_fungible_owners(
                contract_address="",
                network="base"
            )

        with pytest.raises(ValueError, match="contract_address is required and cannot be empty"):
            await mock_client.get_relevant_fungible_owners(
                contract_address="   ",  # whitespace only
                network="base"
            )

    @pytest.mark.asyncio
    async def test_get_relevant_fungible_owners_invalid_network(self, mock_client):
        """Test with invalid network parameter"""
        with pytest.raises(ValueError, match="network must be one of"):
            await mock_client.get_relevant_fungible_owners(
                contract_address="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
                network="invalid_network"
            )

    @pytest.mark.asyncio
    async def test_get_relevant_fungible_owners_invalid_viewer_fid(self, mock_client):
        """Test with invalid viewer_fid parameter"""
        with pytest.raises(ValueError, match="viewer_fid must be a positive integer"):
            await mock_client.get_relevant_fungible_owners(
                contract_address="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
                network="base",
                viewer_fid=0
            )

        with pytest.raises(ValueError, match="viewer_fid must be a positive integer"):
            await mock_client.get_relevant_fungible_owners(
                contract_address="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
                network="base",
                viewer_fid=-1
            )

    @pytest.mark.asyncio
    async def test_get_relevant_fungible_owners_missing_expected_keys(self, mock_client):
        """Test when response is missing expected keys"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "some_other_key": "value"
        }
        mock_client._make_request.return_value = mock_response

        result = await mock_client.get_relevant_fungible_owners(
            contract_address="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
            network="base"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_relevant_fungible_owners_api_error(self, mock_client):
        """Test when API request raises an exception"""
        mock_client._make_request.side_effect = Exception("API error")

        result = await mock_client.get_relevant_fungible_owners(
            contract_address="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
            network="base"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_relevant_fungible_owners_all_networks(self, mock_client):
        """Test with all valid network options"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "top_relevant_fungible_owners_hydrated": [],
            "all_relevant_fungible_owners_dehydrated": []
        }
        mock_client._make_request.return_value = mock_response

        valid_networks = ['ethereum', 'optimism', 'base', 'arbitrum', 'solana']
        
        for network in valid_networks:
            result = await mock_client.get_relevant_fungible_owners(
                contract_address="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
                network=network
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_relevant_fungible_owners_strips_whitespace(self, mock_client):
        """Test that contract address whitespace is stripped"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "top_relevant_fungible_owners_hydrated": [],
            "all_relevant_fungible_owners_dehydrated": []
        }
        mock_client._make_request.return_value = mock_response

        await mock_client.get_relevant_fungible_owners(
            contract_address="  0x833589fcd6edb6e08f4c7c32d4f71b54bda02913  ",
            network="base"
        )

        # Verify whitespace was stripped in the params
        call_args = mock_client._make_request.call_args
        assert call_args[1]["params"]["contract_address"] == "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
