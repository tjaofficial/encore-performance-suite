"""Archive Drawing Board choreography when an enrollment is withdrawn."""
from copy import deepcopy
from .models import DrawingBoard, DrawingBoardWithdrawalSnapshot


def archive_withdrawn_enrollment(enrollment, *, reason="withdrawal"):
    """Capture existing saved positions before changing enrollment status.

    Does not delete or rewrite boards, formations, lighting, or assignments.
    Idempotent for a given board/enrollment. Intended for use in the same
    transaction as the administrator's enrollment change.
    """
    boards = DrawingBoard.objects.filter(
        studio_id=enrollment.student.studio_id,
        class_instance_id=enrollment.class_instance_id,
    ).prefetch_related("formations", "formation_transitions")
    student = enrollment.student
    name = f"{student.first_name} {student.last_name}".strip()
    saved = 0
    for board in boards:
        data = {
            "board_title": board.title,
            "class_id": board.class_instance_id,
            "marker_assignments": deepcopy(board.marker_assignments or []),
            "formations": [
                {"id": form.pk, "name": form.name, "sequence_order": form.sequence_order,
                 "positions": deepcopy(form.positions or [])}
                for form in board.formations.all()
            ],
            "transitions": [
                {"id": transition.pk, "from_id": transition.from_formation_id,
                 "to_id": transition.to_formation_id,
                 "movements": deepcopy(transition.movements or [])}
                for transition in board.formation_transitions.all()
            ],
        }
        _, created = DrawingBoardWithdrawalSnapshot.objects.get_or_create(
            board=board, enrollment_id=enrollment.pk,
            defaults={"student_id": student.pk, "student_name": name,
                      "reason": reason, "snapshot": data},
        )
        saved += int(created)
    return saved
