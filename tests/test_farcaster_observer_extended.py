import pytest
from unittest.mock import AsyncMock
import time
import httpx
from chatbot.integrations.farcaster.observer import FarcasterObserver
from chatbot.core.world_state import WorldStateManager, WorldState, Message

@pytest.fixture
def observer():
    obs = FarcasterObserver(api_key="testkey", signer_uuid="test-signer", bot_fid=1234)
    # Attach a world state manager
    wsm = WorldStateManager()
    obs.world_state_manager = wsm
    return obs

class DummyResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, text=''):
        self.status_code = status_code
        self._json = json_data or {}
        self.headers = headers or {}
        self.text = text
    def json(self):
        return self._json

@pytest.mark.asyncio
async def test_update_rate_limits_and_status(observer):
    # Dummy headers
    headers = {
        'x-ratelimit-limit': '100',
        'x-ratelimit-remaining': '20',
        'x-ratelimit-reset': '3600',
        'x-ratelimit-retry-after': '60'
    }
    response = DummyResponse(status_code=200, json_data={}, headers=headers)
    # Call update
    observer._update_rate_limits(response)
    # Check world state
    state = observer.world_state_manager.state
    assert 'farcaster_api' in state.rate_limits
    info = state.rate_limits['farcaster_api']
    assert info['limit'] == 100
    assert info['remaining'] == 20
    assert info['reset_time'] == 3600
    assert info['retry_after'] == 60
    # Check system_status update
    status = observer.get_rate_limit_status()
    assert status['available'] is True
    assert status['limit'] == 100
    assert status['remaining'] == 20
    assert status['retry_after'] == 60

@pytest.mark.asyncio
async def test_get_rate_limit_status_stale(observer):
    # No rate limit info stored
    observer.world_state_manager.state.rate_limits = {}
    status = observer.get_rate_limit_status()
    assert not status['available']
    # Insert stale info
    observer.world_state_manager.state.rate_limits['farcaster_api'] = {'limit':10,'remaining':5,'last_updated': time.time() - 1000}
    status2 = observer.get_rate_limit_status()
    assert not status2['available']
    assert 'stale' in status2['reason']

@pytest.mark.asyncio
async def test_reply_to_cast_calls_post_cast(observer):
    # Monkeypatch post_cast
    observer.post_cast = AsyncMock(return_value={'success': True, 'cast_hash': 'abc'})
    res = await observer.reply_to_cast("hi there", "hash123")
    observer.post_cast.assert_awaited_once_with(content="hi there", channel=None, reply_to="hash123")
    assert res['success']
    assert res['cast_hash'] == 'abc'

@pytest.mark.asyncio
async def test_observe_home_feed_without_fid(monkeypatch):
    obs = FarcasterObserver(api_key="key", signer_uuid="sid")  # no bot_fid
    obs.world_state_manager = WorldStateManager()
    msgs = await obs._observe_home_feed()
    assert msgs == []

@pytest.mark.asyncio
async def test_format_user_mention_and_context(observer):
    # prepare message
    msg = Message(
        id="1",
        channel_id="farcaster:test",
        channel_type="farcaster",
        sender="user123",
        content="...",
        timestamp=time.time(),
        reply_to=None,
        sender_username="user123",
        sender_display_name="User 123",
        sender_fid=555,
        sender_follower_count=200,
        sender_following_count=50,
        metadata={"power_badge": False, "verified_addresses": {"eth":[]}}
    )
    mention = observer.format_user_mention(msg)
    assert mention == "@user123"
    context = observer.get_user_context(msg)
    assert context['username'] == "user123"
    assert context['display_name'] == "User 123"
    assert context['engagement_level'] == 'medium'

@pytest.mark.asyncio
async def test_quote_and_like_methods(observer, monkeypatch):
    # Monkeypatch httpx AsyncClient with dummy post method accepting self
    async def dummy_post(self, url, headers=None, json=None):
        return DummyResponse(status_code=200, json_data={'cast': {'hash': 'xyz'}})
    class DummyClient:
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): pass
        post = dummy_post
    monkeypatch.setattr(httpx, 'AsyncClient', lambda: DummyClient())
    res_like = await observer.like_cast('cast123')
    assert res_like['success']
    res_quote = await observer.quote_cast('hello', 'cast123')
    assert res_quote['success']
    assert res_quote['quoted_cast'] == 'cast123'

# Note: More tests can be added for _observe_user_feed, _observe_channel_feed, _observe_notifications, _observe_mentions using similar monkeypatch patterns.
