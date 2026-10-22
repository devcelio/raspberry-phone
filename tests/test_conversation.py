from raspberry_phone.conversation import ConversationHistory


def test_history_keeps_only_four_complete_turns() -> None:
    history = ConversationHistory(max_turns=4)

    for number in range(1, 6):
        history.add_turn(f"pergunta {number}", f"resposta {number}")

    assert history.messages() == [
        {"role": "user", "content": "pergunta 2"},
        {"role": "assistant", "content": "resposta 2"},
        {"role": "user", "content": "pergunta 3"},
        {"role": "assistant", "content": "resposta 3"},
        {"role": "user", "content": "pergunta 4"},
        {"role": "assistant", "content": "resposta 4"},
        {"role": "user", "content": "pergunta 5"},
        {"role": "assistant", "content": "resposta 5"},
    ]
