"""学习刷题模块的 Pydantic schemas（请求/响应模型）。"""
from typing import Optional

from pydantic import BaseModel


class OptionOut(BaseModel):
    key: str          # A/B/C/D 或 对/错
    text: str
    is_correct: bool = False


class QuestionOut(BaseModel):
    """题目（不含正确答案，刷题时用）。"""
    id: int
    type: str
    stem: str
    options: list[OptionOut]
    difficulty: int
    knowledge_point_id: Optional[int] = None
    province: Optional[str] = None


class QuestionDetail(QuestionOut):
    """题目详情（含答案与解析，答题后/解析时用）。"""
    answer: str
    analysis: Optional[str] = None


class AnswerIn(BaseModel):
    """提交答案。"""
    question_id: int
    user_answer: str
    time_cost_sec: Optional[int] = None  # 做题耗时


class AnswerResult(BaseModel):
    """判分结果。"""
    question_id: int
    correct: bool
    correct_answer: str
    analysis: Optional[str] = None


class QuizRequest(BaseModel):
    """组卷请求。"""
    count: int = 10
    type: Optional[str] = None          # single/multiple/judge；None=全部
    difficulty: Optional[int] = None     # 1/2/3；None=全部
    knowledge_point_id: Optional[int] = None
    province: Optional[str] = None


class KnowledgePointOut(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    parent_id: Optional[int] = None
    level: int
    description: Optional[str] = None
    question_count: int = 0


class WrongAnswerOut(BaseModel):
    id: int
    question_id: int
    user_answer: str
    reviewed: bool
    question: Optional[QuestionDetail] = None
