"""Request parser (keyword baseline and station matching) and pipeline helpers.
The LLM parser is tested only with TW_LIVE=1, since it calls the LLM API."""
import os

import pytest

from agents.request_parser import keyword_parse, normalize_station, parse_request, penalty_for
from pipeline.build_db import clean_page
from pipeline.load_alerts import clean_mbta_key


@pytest.fixture
def names(graph):
    return sorted(set(graph[1].values()))


@pytest.mark.parametrize("typed, official", [
    ("MGH", "Charles/MGH"), ("logan", "Airport"), ("harvard sq", "Harvard"),
    ("Quincy", "Quincy Center"), ("the Park St station", "Park Street"), ("DTX", "Downtown Crossing"),
    ("Kendall", "Kendall/MIT"), ("nowhere", None),
])
def test_station_names(names, typed, official):
    assert normalize_station(typed, names) == official


def test_keyword_baseline(names):
    p = keyword_parse("From Harvard to Back Bay, avoid Park Street, I hate transfers", names)
    assert (p["origin"], p["destination"], p["avoid"]) == ("Harvard", "Back Bay", ["Park Street"])
    assert penalty_for(p) == 15.0


@pytest.mark.skipif(os.getenv("TW_LIVE") != "1", reason="calls the LLM API; set TW_LIVE=1")
@pytest.mark.parametrize("text, expected", [
    ("wheelchair user, MGH to logan please", ("Charles/MGH", "Airport", [])),
    ("Back Bay to Davis, stay away from Park Street", ("Back Bay", "Davis", ["Park Street"])),
    ("going to Quincy from harvard sq, as few changes as possible", ("Harvard", "Quincy Center", [])),
])
def test_llm_parser(names, text, expected):
    p = parse_request(text, names)
    assert (p["origin"], p["destination"], p["avoid"]) == expected


def test_page_chrome_is_removed():
    page = ("10/14/26, 12:45 AM Accessibility on the MBTA | MBTA\nMenu\nMassachusetts Bay\n"
            "Elevators connect the street to the platform.\nCustomer Support\nLeadership\n"
            "https://www.mbta.com/accessibility 1/8\nAn ofﬁcial website of the City of Boston.")
    assert clean_page(page) == "Elevators connect the street to the platform."


@pytest.mark.parametrize("raw", ["{k}", "{k}\n", "{k}\r\n", '"{k}"', "MBTA_KEY={k}",
                                 "MBTA_KEY={k}\nLLM_API_KEY=sk-abc"])
def test_mbta_key_is_extracted(raw):
    key = "0123456789abcdef0123456789abcdef"
    assert clean_mbta_key(raw.format(k=key)) == key


def test_bad_mbta_key_is_dropped():
    assert clean_mbta_key("not a key") is None and clean_mbta_key("  ") is None
