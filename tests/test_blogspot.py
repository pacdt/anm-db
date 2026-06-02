import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from blogspot_video import (
    resolve_blogger_url,
    _extract_url_regex,
    _extract_url_parser,
    _is_blogger_url,
)


def test_is_blogger_url():
    assert _is_blogger_url("https://www.blogger.com/video.g?token=AD6v5dxpzTTm3WV3Q")
    assert _is_blogger_url("http://www.blogger.com/video.g?token=abc123")
    assert not _is_blogger_url("https://example.com/video.mp4")
    assert not _is_blogger_url("https://bp.blogspot.com/video.mp4")


def test_extract_url_regex_bp_blogspot():
    html = '''
    <html><body>
    <video><source src="https://1.bp.blogspot.com/abc/video.mp4"></video>
    </body></html>
    '''
    result = _extract_url_regex(html)
    assert result == "https://1.bp.blogspot.com/abc/video.mp4"


def test_extract_url_regex_in_script():
    html = '''
    <script>
    var videoUrl = "https://2.bp.blogspot.com/def/stream.m3u8";
    </script>
    '''
    result = _extract_url_regex(html)
    assert result == "https://2.bp.blogspot.com/def/stream.m3u8"


def test_extract_url_regex_file_field():
    html = '''{"file": "https://3.bp.blogspot.com/ghi/video.mp4"}'''
    result = _extract_url_regex(html)
    assert result == "https://3.bp.blogspot.com/ghi/video.mp4"


def test_extract_url_regex_no_match():
    html = "<html><body>No video here</body></html>"
    result = _extract_url_regex(html)
    assert result is None


def test_extract_url_regex_protobuf_url():
    html = '"videoUrl": "https://rr1---sn-ab5s2mek.googlevideo.com/videoplayback?..."'
    result = _extract_url_regex(html)
    assert "googlevideo.com" in result


def test_extract_url_regex_source_src():
    html = '<source src="https://4.bp.blogspot.com/jkl/video.mp4" type="video/mp4">'
    result = _extract_url_regex(html)
    assert result == "https://4.bp.blogspot.com/jkl/video.mp4"


def test_extract_url_parser_source_tag():
    html = '''
    <video controls>
    <source src="https://5.bp.blogspot.com/mno/video.mp4" type="video/mp4">
    </video>
    '''
    result = _extract_url_parser(html)
    assert result == "https://5.bp.blogspot.com/mno/video.mp4"


def test_extract_url_parser_video_tag():
    html = '<video src="https://6.bp.blogspot.com/pqr/video.mp4"></video>'
    result = _extract_url_parser(html)
    assert result == "https://6.bp.blogspot.com/pqr/video.mp4"


def test_extract_url_parser_no_source():
    html = "<html><body>No video</body></html>"
    result = _extract_url_parser(html)
    assert result is None


def test_extract_url_parser_multiple_sources():
    html = '''
    <video>
    <source src="https://7.bp.blogspot.com/first.mp4" type="video/mp4">
    <source src="https://8.bp.blogspot.com/second.mp4" type="video/mp4">
    </video>
    '''
    result = _extract_url_parser(html)
    assert result == "https://7.bp.blogspot.com/first.mp4"


def test_extract_url_protocol_relative():
    html = '<source src="//9.bp.blogspot.com/video.mp4">'
    result = _extract_url_regex(html)
    assert result == "https://9.bp.blogspot.com/video.mp4"


@pytest.mark.asyncio
async def test_resolve_blogger_url_non_blogger():
    url = "https://cdn-s01.mywallpaper-4k-image.net/stream/o/one-piece/01.mp4/index.m3u8"
    session = AsyncMock()
    result = await resolve_blogger_url(url, session)
    assert result == url


@pytest.mark.asyncio
async def test_resolve_blogger_url_regex_hit():
    blogger_url = "https://www.blogger.com/video.g?token=AD6v5dxpzTTm3WV3Q"
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value='<source src="https://1.bp.blogspot.com/abc/video.mp4">')
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    session = AsyncMock()
    session.get = MagicMock(return_value=mock_resp)

    result = await resolve_blogger_url(blogger_url, session)
    assert result == "https://1.bp.blogspot.com/abc/video.mp4"


@pytest.mark.asyncio
async def test_resolve_blogger_url_no_match():
    blogger_url = "https://www.blogger.com/video.g?token=AD6v5dxpzTTm3WV3Q"
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value="<html><body>empty</body></html>")
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    session = AsyncMock()
    session.get = MagicMock(return_value=mock_resp)

    result = await resolve_blogger_url(blogger_url, session)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_blogger_url_http_error():
    blogger_url = "https://www.blogger.com/video.g?token=AD6v5dxpzTTm3WV3Q"
    mock_resp = AsyncMock()
    mock_resp.status = 403
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    session = AsyncMock()
    session.get = MagicMock(return_value=mock_resp)

    result = await resolve_blogger_url(blogger_url, session)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_blogger_url_exception():
    blogger_url = "https://www.blogger.com/video.g?token=AD6v5dxpzTTm3WV3Q"
    session = AsyncMock()
    session.get = MagicMock(side_effect=Exception("connection error"))

    result = await resolve_blogger_url(blogger_url, session)
    assert result is None
