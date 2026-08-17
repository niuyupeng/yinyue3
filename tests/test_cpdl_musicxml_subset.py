from __future__ import annotations

from pathlib import Path

from chorale.cpdl_musicxml_subset import (
    extract_mxl_candidates,
    extract_next_category_url,
    extract_work_links,
    prepare_cpdl_musicxml_subset,
)


def test_extract_work_links_reads_category_page_items() -> None:
    html = """
    <div id="mw-pages"></div>
    <a href="/wiki/index.php/By_a_bank_%28Thomas_Ravenscroft%29" title="By a bank (Thomas Ravenscroft)">By a bank</a>
    <a href="/wiki/index.php/Category:SATB" title="Category:SATB">SATB</a>
    """

    links = extract_work_links(html, "https://www.cpdl.org/wiki/index.php/Category:SATB")

    assert links == [
        {
            "title": "By a bank (Thomas Ravenscroft)",
            "url": "https://www.cpdl.org/wiki/index.php/By_a_bank_%28Thomas_Ravenscroft%29",
        }
    ]


def test_extract_next_category_url_reads_next_page_link() -> None:
    html = '<a href="/wiki/index.php?title=Category:SATB&amp;pagefrom=B#mw-pages" title="Category:SATB">next page</a>'

    url = extract_next_category_url(html, "https://www.cpdl.org/wiki/index.php/Category:SATB")

    assert url == "https://www.cpdl.org/wiki/index.php?title=Category:SATB&pagefrom=B#mw-pages"


def test_extract_mxl_candidates_captures_score_metadata() -> None:
    html = """
    <ul><li><small>(Posted 2001-05-16)</small> <b>CPDL #<font color="brown">02698</font>:</b>
    <a href="/wiki/images/6/6a/Ws-rave-bya.mxl" class="internal" title="Ws-rave-bya.mxl">MusicXML</a></li></ul>
    <dl><dd><b>Score information:</b> Letter <b>Copyright:</b>
    <a href="/wiki/index.php/ChoralWiki:CPDL">CPDL</a></dd></dl>
    """

    candidates = extract_mxl_candidates(html, "https://www.cpdl.org/wiki/index.php/By_a_bank")

    assert candidates[0]["url"] == "https://www.cpdl.org/wiki/images/6/6a/Ws-rave-bya.mxl"
    assert candidates[0]["copyright"] == "CPDL"
    assert candidates[0]["posted"] == "2001-05-16"
    assert candidates[0]["cpdl_number"] == "02698"


def test_prepare_cpdl_musicxml_subset_downloads_non_bach_candidates(tmp_path: Path) -> None:
    category_url = "https://www.cpdl.org/wiki/index.php/Category:SATB"
    category_html = """
    <div id="mw-pages"></div>
    <a href="/wiki/index.php/By_a_bank_%28Thomas_Ravenscroft%29" title="By a bank (Thomas Ravenscroft)">By a bank</a>
    <a href="/wiki/index.php/185_Bach_Chorales_%28Johann_Sebastian_Bach%29" title="185 Bach Chorales (Johann Sebastian Bach)">185 Bach Chorales</a>
    """
    work_html = """
    <ul><li><small>(Posted 2001-05-16)</small> <b>CPDL #<font color="brown">02698</font>:</b>
    <a href="/wiki/images/6/6a/Ws-rave-bya.mxl" class="internal" title="Ws-rave-bya.mxl">MusicXML</a></li></ul>
    <dl><dd><b>Copyright:</b> <a href="/wiki/index.php/ChoralWiki:CPDL">CPDL</a></dd></dl>
    """
    pages = {
        category_url: category_html,
        "https://www.cpdl.org/wiki/index.php/By_a_bank_%28Thomas_Ravenscroft%29": work_html,
    }

    summary = prepare_cpdl_musicxml_subset(
        out_dir=tmp_path / "raw",
        summary_json=tmp_path / "summary.json",
        category_url=category_url,
        max_category_pages=1,
        max_work_pages=10,
        max_files=2,
        request_delay_seconds=0,
        clean=True,
        fetch_text=lambda url: pages[url],
        fetch_bytes=lambda url: b"mxl-bytes:" + url.encode("utf-8"),
    )

    assert summary["status"] == "subset_prepared"
    assert summary["selected_mxl_count"] == 1
    assert "Bach" in summary["skipped"][0]["title"]
    downloaded = Path(summary["records"][0]["local_path"])
    assert downloaded.is_file()
    assert downloaded.read_bytes().startswith(b"mxl-bytes:")


def test_prepare_cpdl_musicxml_subset_skips_missing_copyright(tmp_path: Path) -> None:
    category_url = "https://www.cpdl.org/wiki/index.php/Category:SATB"
    category_html = """
    <div id="mw-pages"></div>
    <a href="/wiki/index.php/No_Copyright_%28Anonymous%29" title="No Copyright (Anonymous)">No Copyright</a>
    """
    work_html = """
    <ul><li><small>(Posted 2001-05-16)</small> <b>CPDL #<font color="brown">02698</font>:</b>
    <a href="/wiki/images/6/6a/no-copyright.mxl" class="internal" title="no-copyright.mxl">MusicXML</a></li></ul>
    <dl><dd><b>Score information:</b> Letter</dd></dl>
    """
    pages = {
        category_url: category_html,
        "https://www.cpdl.org/wiki/index.php/No_Copyright_%28Anonymous%29": work_html,
    }

    summary = prepare_cpdl_musicxml_subset(
        out_dir=tmp_path / "raw",
        summary_json=tmp_path / "summary.json",
        category_url=category_url,
        max_category_pages=1,
        max_work_pages=10,
        max_files=2,
        request_delay_seconds=0,
        fetch_text=lambda url: pages[url],
        fetch_bytes=lambda url: b"should-not-download",
    )

    assert summary["status"] == "no_files_selected"
    assert summary["selected_mxl_count"] == 0
    assert summary["skipped"][0]["reason"] == "copyright missing"
