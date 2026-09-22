"""Sentence-sized CAT segmentation regression tests."""

import core
from transpraxis import segmentation


def test_sentence_mode_splits_prose_but_protects_abbreviations_and_numbers():
    segments, metadata = segmentation.segment_paragraphs([
        "Dr. Smith lives in the U.S. He writes e.g. short examples. "
        "The value is 3.14. Use etc. Next sentence.",
        "Chapter 1. Introduction",
        "- First item. It remains one item.\n- Second item.",
        "这是第一句。这是第二句！",
    ])

    assert segments == [
        "Dr. Smith lives in the U.S.",
        "He writes e.g. short examples.",
        "The value is 3.14.",
        "Use etc.",
        "Next sentence.",
        "Chapter 1. Introduction",
        "- First item. It remains one item.",
        "- Second item.",
        "这是第一句。",
        "这是第二句！",
    ]
    assert metadata["input_paragraph_count"] == 4
    assert metadata["output_segment_count"] == len(segments)
    assert metadata["split_paragraph_count"] == 3
    assert metadata["paragraph_ranges"][-1] == {
        "paragraph_index": 3, "start": 8, "end": 10,
    }


def test_sentence_mode_keeps_tables_urls_and_short_headings_atomic():
    segments, _metadata = segmentation.segment_paragraphs([
        "Name | Value | Note. Another sentence should not split this row.",
        "https://example.org/a.b?q=1",
        "A Short Heading",
    ])

    assert segments == [
        "Name | Value | Note. Another sentence should not split this row.",
        "https://example.org/a.b?q=1",
        "A Short Heading",
    ]


def test_sentence_mode_handles_terminal_punctuation_inside_quotes():
    segments, _metadata = segmentation.segment_paragraphs([
        'He said “Hello.” Next sentence.'
    ])

    assert segments == ['He said “Hello.”', "Next sentence."]


def test_core_helper_keeps_cleaned_paragraphs_separate_from_cat_units():
    state = core.new_job_state("scan.pdf")
    segments, metadata = core._apply_source_segmentation(
        state, ["One sentence. Another sentence."], mode="sentence")

    assert segments == ["One sentence.", "Another sentence."]
    assert state["source_paragraphs"] == ["One sentence. Another sentence."]
    assert state["segmentation"] == metadata
    assert metadata["mode"] == "sentence"


def test_paragraph_mode_remains_available_for_legacy_or_manual_imports():
    segments, metadata = segmentation.segment_paragraphs(
        ["One. Two.", "Three."], mode="paragraph")

    assert segments == ["One. Two.", "Three."]
    assert metadata["mode"] == "paragraph"
    assert metadata["split_paragraph_count"] == 0


def test_core_defaults_non_pdf_imports_to_legacy_paragraph_units():
    state = core.new_job_state("book.docx")

    segments, metadata = core.segment_source_paragraphs(
        ["One sentence. Another sentence."], state=state)

    assert segments == ["One sentence. Another sentence."]
    assert metadata["mode"] == "paragraph"
