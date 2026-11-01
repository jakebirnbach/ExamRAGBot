from study_assistant.infrastructure.parsing.text_cleaning import clean_page_text


def test_removes_page_footer_and_transcript_header() -> None:
    raw = " \n \n1 | P a g e \n \n \nVideo Transcript \nSelf-Efficacy \n"
    assert clean_page_text(raw) == "Self-Efficacy"


def test_normalises_ligatures_and_bullets() -> None:
    assert clean_page_text(" ﬁnd conﬁdence") == "• find confidence"


def test_collapses_whitespace_but_keeps_paragraphs() -> None:
    assert clean_page_text("a   b\n\n\n\n c") == "a b\n\nc"
