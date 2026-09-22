from db.db_status import is_connectivity_failure


def test_integrity_errors_are_not_misclassified_as_database_outage() -> None:
    error = RuntimeError(
        'insert or update on table "chat_messages" violates foreign key constraint '
        '"chat_messages_session_id_fkey"'
    )

    assert is_connectivity_failure(error) is False


def test_real_connection_failure_remains_an_availability_failure() -> None:
    assert is_connectivity_failure(RuntimeError("connection refused by database")) is True
