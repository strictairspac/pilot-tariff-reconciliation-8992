from fastapi import APIRouter, Depends

from src.config.resources import engine
from src.controllers.access import identity, operator
from src.controllers.workbench import new_supplement, retry_supplement, retire_supplement
from src.schemas.supplements import SupplementEntry, SupplementInput
from src.services import supplements

router = APIRouter(prefix="/supplements", tags=["Supplements"])


@router.get("", response_model=list[SupplementEntry], dependencies=[Depends(identity)])
def list_supplements():
    with engine.connect() as db:
        return supplements.list_entries(db)


@router.get("/{supplement_id}", response_model=SupplementEntry, dependencies=[Depends(identity)])
def supplement_detail(supplement_id: int):
    with engine.connect() as db:
        return supplements.get(db, supplement_id)


@router.post("", response_model=SupplementEntry, status_code=201)
def register(form: SupplementInput, user=Depends(operator)):
    return new_supplement(form, user)


@router.post("/{supplement_id}/retry", response_model=SupplementEntry)
def retry(supplement_id: int, user=Depends(operator)):
    return retry_supplement(supplement_id, user)


@router.post("/{supplement_id}/retire", response_model=SupplementEntry)
def retire(supplement_id: int, user=Depends(operator)):
    return retire_supplement(supplement_id, user)
