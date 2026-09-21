# =================================================================
#
# Authors: Tom Kralidis <tomkralidis@gmail.com>
#
# Copyright (c) 2026 Tom Kralidis
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# =================================================================

import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from pygeoapi.api import APIRequest
from pygeoapi.api.stac import search, landing_page
from pygeoapi.formats import FORMAT_TYPES, F_JSON
from pygeoapi.util import yaml_load

from tests.util import get_test_file_path, mock_api_request


@pytest.fixture()
def config():
    with open(get_test_file_path('pygeoapi-test-stac-api-config.yml')) as fh:
        return yaml_load(fh)


def test_landing_page(config, api_):
    req = mock_api_request()
    rsp_headers, code, response = landing_page(api_, req)
    response = json.loads(response)

    assert rsp_headers['Content-Type'] == 'application/json' == \
           FORMAT_TYPES[F_JSON]

    assert isinstance(response, dict)
    assert 'links' in response
    assert len(response['conformsTo']) == 3
    assert response['type'] == 'Catalog'
    assert response['links'][0]['rel'] == 'self'
    assert response['links'][0]['type'] == 'application/json'
    assert response['links'][0]['href'] == 'http://localhost:5000/stac-api?f=json'  # noqa
    assert len(response['links']) == 5
    assert 'title' in response
    assert response['title'] == 'pygeoapi default instance'
    assert 'description' in response
    assert response['description'] == 'pygeoapi provides an API to geospatial data'  # noqa


@pytest.mark.parametrize('params,matched,returned', [
    ({}, 10, 10),
    ({'bbox': '-142,52,-140,55'}, 6, 6),
    ({'limit': '1'}, 10, 1),
    ({'datetime': '2019-11-11T11:11:11Z/..'}, 6, 6),
    ({'datetime': '2018-11-11T11:11:11Z/2019-11-11T11:11:11Z'}, 4, 4)
])
def test_search(config, api_, params, matched, returned):
    # test GET
    req = mock_api_request(params)
    rsp_headers, code, response = search(api_, req)
    response = json.loads(response)

    assert response['numberMatched'] == matched
    assert response['numberReturned'] == returned

    for feature in response['features']:
        assert feature['stac_version'] == '1.0.0'

    # test POST
    req = mock_api_request(data=params)
    rsp_headers, code, response = search(api_, req)
    response = json.loads(response)

    assert response['numberMatched'] == matched
    assert response['numberReturned'] == returned

    for feature in response['features']:
        assert feature['stac_version'] == '1.0.0'


@pytest.mark.parametrize('post_data,limit', [(None, 3), ({'limit': 2}, 2)])
def test_search_django_query_params(api_, post_data, limit, monkeypatch):
    """Django query values stay scalar in POST overrides and paging links."""
    django_http = pytest.importorskip('django.http')
    monkeypatch.setattr(django_http.request, 'settings', SimpleNamespace(
        DATA_UPLOAD_MAX_NUMBER_FIELDS=1000))
    params = django_http.QueryDict(
        'limit=1&limit=3&offset=2&bbox=-180,-90,180,90', encoding='utf-8')
    request = SimpleNamespace(
        GET=params, headers={}, path_info='/stac-api/search',
        body=json.dumps(post_data).encode() if post_data else b'')
    req = APIRequest.from_django(request, api_.locales)

    _, code, response = search(api_, req)
    assert code == 200
    response = json.loads(response)
    assert response['numberMatched'] == 10
    assert response['numberReturned'] == limit
    links = {link['rel']: link['href'] for link in response['links']}
    for rel, offset in [('prev', None), ('next', [str(2 + limit)])]:
        query = parse_qs(urlsplit(links[rel]).query)
        assert query['limit'] == [str(limit)]
        assert query['bbox'] == ['-180,-90,180,90']
        assert query.get('offset') == offset
    assert params.getlist('limit') == ['1', '3']
    assert params['offset'] == '2'
