class InvalidDoctorAssignmentError(ValueError):
    pass


def normalize_single_doctor_id(raw: str | None) -> str:
    doctor_id = (raw or "").strip()
    if not doctor_id:
        raise InvalidDoctorAssignmentError("assigned_doctor_id is required")
    if "," in doctor_id:
        raise InvalidDoctorAssignmentError("A case can be assigned to only one doctor")
    return doctor_id

