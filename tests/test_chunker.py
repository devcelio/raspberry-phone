from raspberry_phone.chunking import SentenceChunker


def test_chunker_emits_complete_sentences_and_flushes_tail() -> None:
    chunker = SentenceChunker(max_chars=180)

    assert chunker.feed("Oi! Eu sou o tele") == ["Oi!"]
    assert chunker.feed("fone. Tudo bem") == ["Eu sou o telefone."]
    assert chunker.flush() == ["Tudo bem"]


def test_chunker_breaks_long_unpunctuated_text_at_a_space() -> None:
    chunker = SentenceChunker(max_chars=24)

    emitted = chunker.feed("uma resposta comprida sem pontuacao final")

    assert emitted == ["uma resposta comprida"]
    assert chunker.flush() == ["sem pontuacao final"]


def test_chunker_treats_newlines_as_boundaries() -> None:
    chunker = SentenceChunker()

    assert chunker.feed("primeira linha\nsegunda linha") == ["primeira linha"]
    assert chunker.flush() == ["segunda linha"]


def test_decimal_across_deltas_is_not_a_sentence_boundary():
    chunker = SentenceChunker()
    assert chunker.feed('O valor é 3.') == []
    assert chunker.feed('5 reais. Tudo certo?') == ['O valor é 3.5 reais.', 'Tudo certo?']


def test_first_clause_can_start_voice_before_sentence_finishes():
    chunker = SentenceChunker()
    assert chunker.feed('Para preparar o arroz com tomate, primeiro') == ['Para preparar o arroz com tomate,']
    assert chunker.flush() == ['primeiro']
