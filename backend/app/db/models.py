"""数据模型 —— 三大业务域：学习刷题 / 政策公告 / 交易模拟。

设计原则：
- 对齐电力交易员国家职业标准与统考题型（单选/多选/判断）
- 政策模型统一，可承载飞书知识库基线 + 各省爬虫增量
- 交易模型覆盖中长期/现货/辅助服务/绿电
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def now_utc() -> datetime:
    """当前 UTC 时间（naive，去掉 tzinfo）。

    替代 datetime 的已弃用 UTC 取时写法（Py3.12 起 DeprecationWarning）。
    本仓库所有 DateTime 列均为 naive（SQLite 未启用 timezone=True），
    且既有测试用 naive 断言比较；返回 naive UTC 可与 DB 列及测试断言
    无缝比较，避免 aware/naive 混比触发 TypeError。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==================== 通用混入 ====================

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# ==================== 模块0：用户体系（系统基座）================

class User(Base, TimestampMixin):
    """系统用户 —— 支持注册登录、数据隔离、角色权限。

    所有业务数据（学习/交易/考试）通过 user_id 关联到此表，
    实现多用户数据隔离。
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, comment="用户名")
    email: Mapped[Optional[str]] = mapped_column(String(100), index=True, comment="邮箱")
    hashed_password: Mapped[str] = mapped_column(String(200), comment="bcrypt哈希")
    display_name: Mapped[Optional[str]] = mapped_column(String(50), comment="显示名")
    avatar: Mapped[Optional[str]] = mapped_column(String(500), comment="头像URL")
    role: Mapped[str] = mapped_column(String(20), default="user", comment="user/admin/student")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    # 学习目标
    target_level: Mapped[Optional[str]] = mapped_column(String(10), comment="备考目标: intermediate/senior")
    home_province: Mapped[Optional[str]] = mapped_column(String(20), comment="所在省份")
    # 最后活跃
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class UserLLMConfig(Base, TimestampMixin):
    """每用户独立的 BYOK 模型配置；API Key 仅保存加密密文。"""
    __tablename__ = "user_llm_configs"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_llm_config_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(30), default="none")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    model: Mapped[str] = mapped_column(String(150), default="")
    encrypted_api_key: Mapped[Optional[str]] = mapped_column(Text)
    api_key_hint: Mapped[Optional[str]] = mapped_column(String(20))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AIChatHistory(Base, TimestampMixin):
    """AI 助手聊天历史 —— 用户与AI助手的问答记录。"""
    __tablename__ = "ai_chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    sources: Mapped[Optional[str]] = mapped_column(Text, comment="引用来源JSON")
    mode: Mapped[Optional[str]] = mapped_column(String(20), comment="rag/fallback_chunk/no_match")


# ==================== 模块A：学习刷题 ====================

class KnowledgePoint(Base, TimestampMixin):
    """知识点 —— 构成知识体系树（行业认知→批发→零售→中长期→现货→...）。"""
    __tablename__ = "knowledge_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    code: Mapped[Optional[str]] = mapped_column(String(50), unique=True, comment="如 spot.lmp")
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("knowledge_points.id"))
    level: Mapped[int] = mapped_column(Integer, default=1, comment="层级1-3")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[Optional[str]] = mapped_column(Text)

    children: Mapped[list["KnowledgePoint"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    parent: Mapped[Optional["KnowledgePoint"]] = relationship(
        back_populates="children", remote_side=[id]
    )


class KnowledgePointPrerequisite(Base, TimestampMixin):
    """知识点前置关系 —— "学 X 之前先懂 P"。

    联结表：kp_id 是要学的知识点，prereq_kp_id 是它的前置知识点。
    UniqueConstraint(kp_id, prereq_kp_id) 防止重复边。
    """
    __tablename__ = "knowledge_point_prerequisites"
    __table_args__ = (
        UniqueConstraint("kp_id", "prereq_kp_id", name="uq_kp_prerequisite"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kp_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id"), index=True, nullable=False,
        comment="要学的知识点",
    )
    prereq_kp_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id"), index=True, nullable=False,
        comment="前置知识点",
    )


class Question(Base, TimestampMixin):
    """题库题目 —— 对齐统考题型：单选/多选/判断。"""
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 题型：single 单选 / multiple 多选 / judge 判断
    type: Mapped[str] = mapped_column(String(20), index=True)
    stem: Mapped[str] = mapped_column(Text, comment="题干")
    # JSON 数组：[{"key":"A","text":"...","is_correct":true}, ...]
    options: Mapped[str] = mapped_column(Text, comment="JSON格式选项")
    answer: Mapped[str] = mapped_column(String(200), comment="正确答案，如 ABC / 对")
    analysis: Mapped[Optional[str]] = mapped_column(Text, comment="解析")

    difficulty: Mapped[int] = mapped_column(Integer, default=2, comment="1易 2中 3难")
    knowledge_point_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("knowledge_points.id"), index=True
    )
    province: Mapped[Optional[str]] = mapped_column(String(20), index=True, comment="省份相关题，如 浙江")
    source: Mapped[Optional[str]] = mapped_column(String(100), comment="来源，如 飞书题库V2")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ---- 多源题库扩展 ----
    source_type: Mapped[str] = mapped_column(
        String(20), default="manual", comment="manual/feishu/ai_generated/crawler 官方/文档/知乎B站"
    )
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), comment="原始来源URL")
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, comment="AI生成题")
    # 真题标记：年份+级别，用于历年分析
    is_real_exam: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否历年真题回忆")
    exam_year: Mapped[Optional[int]] = mapped_column(Integer, comment="真题年份")
    exam_level: Mapped[Optional[str]] = mapped_column(String(20), comment="four四级/three三级...")
    # 考点预测：标记此题对应当年高频/新增考点
    prediction_tags: Mapped[Optional[str]] = mapped_column(Text, comment="JSON:预测标签如高频/新增/政策关联")
    # 去重：题干hash，外部题库导入去重用
    stem_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True, comment="题干hash去重")


class Course(Base, TimestampMixin):
    """课程 —— 分层：新人入职/全员基础/进阶专题/备考冲刺。"""
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True, comment="onboarding/basic/advanced/exam")
    summary: Mapped[Optional[str]] = mapped_column(Text)
    cover_url: Mapped[Optional[str]] = mapped_column(String(500))
    knowledge_point_id: Mapped[Optional[int]] = mapped_column(ForeignKey("knowledge_points.id"))
    province: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="course", cascade="all, delete-orphan")


class Lesson(Base, TimestampMixin):
    """课时。"""
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[Optional[str]] = mapped_column(Text, comment="正文(markdown/html)")
    media_url: Mapped[Optional[str]] = mapped_column(String(500), comment="视频/PDF地址")
    media_type: Mapped[Optional[str]] = mapped_column(String(20), comment="video/pdf/doc")
    duration_min: Mapped[int] = mapped_column(Integer, default=0, comment="时长(分钟)")
    sort: Mapped[int] = mapped_column(Integer, default=0)

    course: Mapped["Course"] = relationship(back_populates="lessons")


class StudyRecord(Base, TimestampMixin):
    """学习记录。"""
    __tablename__ = "study_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1, index=True)  # 本地起步单用户
    lesson_id: Mapped[Optional[int]] = mapped_column(ForeignKey("lessons.id"))
    question_id: Mapped[Optional[int]] = mapped_column(ForeignKey("questions.id"))
    action: Mapped[str] = mapped_column(String(20), comment="view/answer/correct/wrong/mark")
    detail: Mapped[Optional[str]] = mapped_column(Text, comment="JSON: 用户答案/耗时等")


class UserProfile(Base, TimestampMixin):
    """用户能力档案 —— 支撑学习刷题的分层（L1/L2/L3）。

    L1 零基础：完全没经验，从行业概念学起
    L2 进阶：有经验，系统学习+跟政策
    L3 老手：只看变动，政策对比/省份动态/新增考点
    """
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1, unique=True, index=True)
    # 能力层级：L1零基础 / L2进阶 / L3老手
    level: Mapped[str] = mapped_column(String(10), default="L1", index=True)
    # 主省份：深入学习的省份
    home_province: Mapped[Optional[str]] = mapped_column(String(20), default="浙江")
    # 诊断结果 JSON: {score, correct_rates_by_module, recommended_level}
    diagnosis: Mapped[Optional[str]] = mapped_column(Text)
    # 学习进度：各知识点掌握度 JSON {kp_code: mastery_pct}
    mastery: Mapped[Optional[str]] = mapped_column(Text, default="{}")
    # 诊断时间
    last_diagnosed_at: Mapped[Optional[str]] = mapped_column(String(30))
    # 是否完成诊断
    diagnosed: Mapped[bool] = mapped_column(Boolean, default=False)

    # ---- 用户可自由调整的偏好（诊断只推荐，不锁定）----
    # 用户手动选择的层级（覆盖诊断结果）；None=跟随诊断
    manual_level: Mapped[Optional[str]] = mapped_column(String(10), comment="用户手选层级，优先于诊断")
    # 偏好难度：1简单 / 2中等 / 3困难 / 0自适应
    preferred_difficulty: Mapped[int] = mapped_column(Integer, default=0, comment="0自适应/1简单/2中等/3困难")
    # 关注的省份列表 JSON: ["浙江","山西",...]（主省份始终在其中）
    watched_provinces: Mapped[Optional[str]] = mapped_column(Text, default='["浙江"]', comment="关注省份JSON")
    # 关注的内容类型 JSON: ["policy","quiz","scenario",...]
    content_interests: Mapped[Optional[str]] = mapped_column(Text, default='["all"]', comment="关注内容类型")
    # 每日学习目标（题数）
    daily_goal: Mapped[int] = mapped_column(Integer, default=10, comment="每日刷题目标")


class LearningPath(Base, TimestampMixin):
    """学习路径 —— 按层级组织的引导式学习序列。

    L1: 行业认知→市场主体→电价基础→交易品种入门
    L2: 中长期→现货→辅助服务→结算→各省规则对比
    L3: 最新政策→变动对比→省份动态→新增考点速刷
    """
    __tablename__ = "learning_paths"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[str] = mapped_column(String(10), index=True, comment="L1/L2/L3")
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    # 步骤 JSON: [{order, title, type(lesson/quiz/policy), ref_id, required}, ...]
    steps: Mapped[str] = mapped_column(Text, comment="学习步骤JSON")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    province: Mapped[Optional[str]] = mapped_column(String(20), comment="省份专属路径，None=通用")
    # 完成该路径所需的步骤数
    total_steps: Mapped[int] = mapped_column(Integer, default=0)


class GuidedLessonProgress(Base, TimestampMixin):
    """主动引导课程进度 —— 每课必须产出可检查的业务成果。"""
    __tablename__ = "guided_lesson_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "unit_code", name="uq_guided_lesson_user_unit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    unit_code: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="not_started", comment="not_started/in_progress/completed"
    )
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    deliverable_text: Mapped[Optional[str]] = mapped_column(Text)
    check_score: Mapped[Optional[float]] = mapped_column(Float)
    # JSON数组：每次即时检查的逐题选择、判分、正确答案与解析快照
    check_attempts: Mapped[Optional[str]] = mapped_column(Text, default="[]")
    started_at: Mapped[Optional[str]] = mapped_column(String(40))
    completed_at: Mapped[Optional[str]] = mapped_column(String(40))


class LearningBook(Base, TimestampMixin):
    """用户自定义教材 —— 原文件、MinerU派生Markdown与行业准入状态。"""
    __tablename__ = "learning_books"
    __table_args__ = (
        UniqueConstraint("user_id", "raw_sha256", name="uq_learning_book_user_file"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(300))
    original_filename: Mapped[str] = mapped_column(String(300))
    file_type: Mapped[str] = mapped_column(String(20))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    raw_sha256: Mapped[str] = mapped_column(String(64), index=True)
    raw_path: Mapped[str] = mapped_column(String(1000))
    markdown_path: Mapped[Optional[str]] = mapped_column(String(1000))
    parser_engine: Mapped[Optional[str]] = mapped_column(String(50))
    parser_status: Mapped[str] = mapped_column(
        String(20), default="processing",
        comment="processing/ready/rejected/failed",
    )
    parser_message: Mapped[Optional[str]] = mapped_column(Text)
    industry_relevance: Mapped[Optional[float]] = mapped_column(Float)
    relevance_reason: Mapped[Optional[str]] = mapped_column(Text)
    chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    current_chapter_id: Mapped[Optional[int]] = mapped_column(Integer)


class LearningBookChapter(Base, TimestampMixin):
    """教材章节 —— 从Markdown标题结构拆分出的可学习单元。"""
    __tablename__ = "learning_book_chapters"
    __table_args__ = (
        UniqueConstraint("book_id", "chapter_order", name="uq_learning_book_chapter_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("learning_books.id"), index=True)
    chapter_order: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    markdown_content: Mapped[str] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    key_points: Mapped[Optional[str]] = mapped_column(Text, default="[]")
    quiz_json: Mapped[Optional[str]] = mapped_column(Text, default="[]")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    source_page_start: Mapped[Optional[int]] = mapped_column(Integer)
    source_page_end: Mapped[Optional[int]] = mapped_column(Integer)


class LearningBookProgress(Base, TimestampMixin):
    """用户逐章学习记录、笔记和章节测验结果。"""
    __tablename__ = "learning_book_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "chapter_id", name="uq_learning_book_user_chapter"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("learning_books.id"), index=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("learning_book_chapters.id"), index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="not_started", comment="not_started/in_progress/completed"
    )
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    quiz_score: Mapped[Optional[float]] = mapped_column(Float)
    quiz_attempts: Mapped[Optional[str]] = mapped_column(Text, default="[]")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[str]] = mapped_column(String(40))
    completed_at: Mapped[Optional[str]] = mapped_column(String(40))


class ProvinceConfig(Base, TimestampMixin):
    """省份配置 —— 各省份交易规则、现货试点、平台信息。

    支撑主省份深入 + 其他省份对比。
    """
    __tablename__ = "province_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    grid: Mapped[str] = mapped_column(String(10), comment="sgcc国网/csg南网/impc蒙西")
    spot_pilot: Mapped[Optional[str]] = mapped_column(String(50), comment="现货试点批次")
    spot_status: Mapped[Optional[str]] = mapped_column(String(50), comment="现货运行状态")
    platform_url: Mapped[Optional[str]] = mapped_column(String(200))
    info_path: Mapped[Optional[str]] = mapped_column(String(200), comment="信息公开路径")
    # 交易规则摘要
    rule_summary: Mapped[Optional[str]] = mapped_column(Text, comment="该省交易规则要点")
    # 与主省份的关键差异 JSON
    differences: Mapped[Optional[str]] = mapped_column(Text, comment="与他省差异要点JSON")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WrongAnswer(Base, TimestampMixin):
    """错题本。"""
    __tablename__ = "wrong_answers"
    # 真实唯一约束 —— 防止并发提交在同一 user+question 上产生重复行。
    # 之前仅靠 submit_answer 的 query-before-insert 去重，并发滑会 dupe。
    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_wrong_answer_user_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    user_answer: Mapped[str] = mapped_column(String(200))
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已复习掌握")
    # 间隔重复：下次复习时间与当前间隔(天)。首次答错时 interval=1。
    next_review_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, index=True, comment="下次到期复习时间"
    )
    review_interval: Mapped[int] = mapped_column(
        Integer, default=1, comment="当前复习间隔(天)，1→2→4→7→14→30 封顶"
    )


class AnswerLog(Base, TimestampMixin):
    """答题流水 —— append-only 记录每次作答(对+错)，用于掌握度计算。

    与 WrongAnswer 互补：WrongAnswer 仅记错题且按 user+question 去重；
    AnswerLog 记全部尝试，按 kp 聚合算 correct/total 即得掌握度。
    kp_id 是 Question.knowledge_point_id 的快照(反范式)，免去每次 join。
    """
    __tablename__ = "answer_logs"
    __table_args__ = (
        Index("ix_answer_logs_user_kp", "user_id", "kp_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id"), index=True
    )
    kp_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("knowledge_points.id"), nullable=True, index=True,
        comment="反范式：Question.knowledge_point_id 快照，便于按 KP 聚合",
    )
    is_correct: Mapped[bool] = mapped_column(Boolean)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, index=True)


class ConceptReading(Base, TimestampMixin):
    """概念阅读状态 —— KnowledgeBook 概念页的阅读进度(read/understood)。"""
    __tablename__ = "concept_readings"
    __table_args__ = (
        UniqueConstraint("user_id", "concept_code", name="uq_concept_reading_user_concept"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    concept_code: Mapped[str] = mapped_column(String(50), comment="概念编码如 321")
    status: Mapped[str] = mapped_column(
        String(20), comment="read 已读 / understood 已懂"
    )


# ---- 考试刷题模块（双模式：学习知识驱动 / 考试智能押题）----

class ExamBlueprint(Base, TimestampMixin):
    """考试蓝图 —— 真实统考的题型配比与各模块权重。

    来源：2024国家职业标准 + 历年真题统计。
    这是组卷和考点预测的 ground truth。
    """
    __tablename__ = "exam_blueprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), comment="如 中级工理论 / 高级工理论")
    level: Mapped[str] = mapped_column(String(20), index=True, comment="four/three/two/one")
    # 题型配比 JSON: {"single":{"count":100,"score":0.5},"multiple":{"count":30,"score":1},"judge":{"count":40,"score":0.5}}
    type_config: Mapped[str] = mapped_column(Text, comment="题型数量与分值JSON")
    total_score: Mapped[float] = mapped_column(Float, default=100.0)
    pass_score: Mapped[float] = mapped_column(Float, default=60.0)
    duration_min: Mapped[int] = mapped_column(Integer, default=90)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ExamWeight(Base, TimestampMixin):
    """各知识模块在考试中的权重（占比%）—— 来自国家职业标准权重表。

    用于考点预测：权重高的模块多出题。
    """
    __tablename__ = "exam_weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blueprint_id: Mapped[int] = mapped_column(ForeignKey("exam_blueprints.id"), index=True)
    knowledge_point_id: Mapped[Optional[int]] = mapped_column(ForeignKey("knowledge_points.id"))
    module_name: Mapped[str] = mapped_column(String(100), comment="模块名，如 市场交易规则")
    weight_pct: Mapped[float] = mapped_column(Float, comment="占比%")
    level: Mapped[str] = mapped_column(String(20), comment="four/three/...")
    # 预测调整：基于政策更新动态调整的权重加成
    prediction_boost: Mapped[float] = mapped_column(Float, default=0.0, comment="预测权重加成")


class ExamSession(Base, TimestampMixin):
    """一次考试会话（模考记录）。"""
    __tablename__ = "exam_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    blueprint_id: Mapped[Optional[int]] = mapped_column(ForeignKey("exam_blueprints.id"))
    mode: Mapped[str] = mapped_column(String(20), comment="exam考试 / predict押题模考")
    level: Mapped[Optional[str]] = mapped_column(String(20), comment="four/three/two/one")
    # 抽到的题目ID列表 JSON
    question_ids: Mapped[str] = mapped_column(Text, comment="JSON题目ID数组")
    # 答题记录 JSON: [{question_id, user_answer, correct, time_cost}, ...]
    answers: Mapped[Optional[str]] = mapped_column(Text, default="[]")
    score: Mapped[Optional[float]] = mapped_column(Float, comment="得分")
    started_at: Mapped[Optional[str]] = mapped_column(String(30))
    finished_at: Mapped[Optional[str]] = mapped_column(String(30))
    # 考后薄弱点分析 JSON
    weak_analysis: Mapped[Optional[str]] = mapped_column(Text, comment="薄弱模块分析")
    status: Mapped[str] = mapped_column(String(20), default="ongoing", comment="ongoing/finished")


# ==================== 模块B：政策公告 ====================

class Policy(Base, TimestampMixin):
    """政策 / 公告 / 信息披露 —— 统一文档模型。

    数据源：飞书知识库2基线 + 各省爬虫增量。
    """
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    publish_date: Mapped[Optional[str]] = mapped_column(String(20), index=True, comment="发布日期 YYYY-MM-DD")
    publish_date_status: Mapped[str] = mapped_column(
        String(20), default="unverified", index=True, comment="verified/unverified/imported"
    )
    publish_date_evidence: Mapped[Optional[str]] = mapped_column(
        String(100), comment="发布日期提取证据，如 meta:datepublished"
    )
    publish_date_verified_at: Mapped[Optional[str]] = mapped_column(String(40))
    doc_number: Mapped[Optional[str]] = mapped_column(String(200), comment="文号，如 国办发〔2026〕4号")

    # 分类：national 国家政策 / market 市场公告 / clearing 出清结果 / regulation 交易规则
    category: Mapped[str] = mapped_column(String(30), index=True)
    province: Mapped[Optional[str]] = mapped_column(String(20), index=True, comment="省份；国家级为空")

    source: Mapped[str] = mapped_column(String(100), comment="来源：feishu/zjpx/csg/...")
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    content: Mapped[Optional[str]] = mapped_column(Text, comment="正文摘要或全文")

    # AI 解读（LLM 生成，可空）
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, comment="一段话看懂")
    ai_analysis: Mapped[Optional[str]] = mapped_column(Text, comment="对交易的影响分析")
    ai_interpreted: Mapped[bool] = mapped_column(Boolean, default=False)

    # 推送/阅读
    priority: Mapped[int] = mapped_column(Integer, default=0, comment="0普通 1重要 2紧急")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    attachments: Mapped[list["PolicyAttachment"]] = relationship(
        back_populates="policy", cascade="all, delete-orphan"
    )

    # 去重键：标题+日期的 hash，爬虫增量更新用
    dedup_key: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)


class PolicyRead(Base, TimestampMixin):
    """每用户政策阅读状态，避免一个用户的操作污染其他用户。"""
    __tablename__ = "policy_reads"
    __table_args__ = (
        UniqueConstraint("user_id", "policy_id", name="uq_policy_read_user_policy"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), index=True)


class PolicyAttachment(Base, TimestampMixin):
    """政策附件（PDF/Word）。"""
    __tablename__ = "policy_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    file_type: Mapped[str] = mapped_column(String(20), comment="pdf/doc/...")
    file_url: Mapped[Optional[str]] = mapped_column(String(1000), comment="原始URL")
    local_path: Mapped[Optional[str]] = mapped_column(String(500), comment="本地下载路径")

    policy: Mapped["Policy"] = relationship(back_populates="attachments")


# ==================== 模块C：交易模拟 ====================

class TradeMarket(Base, TimestampMixin):
    """市场/品种定义 —— 对齐真实市场结构。"""
    __tablename__ = "trade_markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 品种：mid_long_term 中长期 / day_ahead 日前 / realtime 实时 / freq 调频 / green 绿电
    product: Mapped[str] = mapped_column(String(30), index=True)
    product_label: Mapped[str] = mapped_column(String(50))
    province: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)


class TradeOrder(Base, TimestampMixin):
    """用户申报订单。"""
    __tablename__ = "trade_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("trade_markets.id"), index=True)
    side: Mapped[str] = mapped_column(String(10), comment="buy 买(用电) / sell 卖(发电)")
    # 报价曲线：JSON [{time:"01:00",price:320,volume:500}, ...]
    bid_curve: Mapped[str] = mapped_column(Text, comment="申报量价曲线JSON")
    total_volume: Mapped[float] = mapped_column(Float, comment="总申报量MWh")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="pending/filled/canceled")


class TradeTrade(Base, TimestampMixin):
    """成交记录。"""
    __tablename__ = "trade_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("trade_markets.id"), index=True)
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trade_orders.id"))
    side: Mapped[str] = mapped_column(String(10))
    price: Mapped[float] = mapped_column(Float, comment="成交价 元/MWh")
    volume: Mapped[float] = mapped_column(Float, comment="成交量 MWh")
    clearing_price: Mapped[Optional[float]] = mapped_column(Float, comment="出清价")
    trade_time: Mapped[Optional[str]] = mapped_column(String(30))


class TradePosition(Base, TimestampMixin):
    """持仓与结算。"""
    __tablename__ = "trade_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("trade_markets.id"), index=True)
    net_volume: Mapped[float] = mapped_column(Float, default=0, comment="净持仓量")
    avg_price: Mapped[float] = mapped_column(Float, default=0, comment="均价")
    pnl: Mapped[float] = mapped_column(Float, default=0, comment="浮动盈亏")


class TradeAccount(Base, TimestampMixin):
    """模拟交易账户。"""
    __tablename__ = "trade_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1, unique=True)
    balance: Mapped[float] = mapped_column(Float, default=1_000_000.0, comment="模拟资金")
    frozen: Mapped[float] = mapped_column(Float, default=0, comment="冻结资金")


class SimulationSession(Base, TimestampMixin):
    """单人仿真任务实例 —— 不依赖房间，完整保存输入、申报、出清和结算快照。"""
    __tablename__ = "simulation_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    scenario_code: Mapped[str] = mapped_column(String(50), index=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("trade_markets.id"), index=True)
    province: Mapped[str] = mapped_column(String(20), index=True)
    trade_date: Mapped[str] = mapped_column(String(20), index=True)
    role: Mapped[str] = mapped_column(String(30), comment="retailer/generator")
    stage: Mapped[str] = mapped_column(
        String(20), default="briefing",
        comment="briefing/bidding/sealed/cleared/settled",
    )
    period_count: Mapped[int] = mapped_column(Integer, default=24)
    rules_version: Mapped[str] = mapped_column(String(50))
    engine_version: Mapped[str] = mapped_column(String(50))
    random_seed: Mapped[int] = mapped_column(Integer)
    input_snapshot: Mapped[str] = mapped_column(Text)
    orders_snapshot: Mapped[Optional[str]] = mapped_column(Text)
    clearing_result: Mapped[Optional[str]] = mapped_column(Text)
    settlement_result: Mapped[Optional[str]] = mapped_column(Text)
    review_result: Mapped[Optional[str]] = mapped_column(Text)


# ==================== 模块E：数据资产中心（系统基座）================

class CategoryNode(Base, TimestampMixin):
    """分类树节点 —— 电力市场完整业务版图的科学分类骨架。

    设计：主分类树（8章业务导航）+ 多维交叉标签
    编码：数字编码（如311=电能量市场/中长期），便于机器归类和URL生成
    来源：国家发改委/能源局/中电联权威口径，覆盖全行业
    """
    __tablename__ = "category_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, comment="数字编码如311")
    name: Mapped[str] = mapped_column(String(100), index=True)
    parent_code: Mapped[Optional[str]] = mapped_column(String(10), index=True)
    level: Mapped[int] = mapped_column(Integer, default=1, comment="1章/2节/3子节")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # 维度标识：chapter(主分类) / entity(主体) / product(品种) / level(层级) / region(地域)
    facet: Mapped[str] = mapped_column(String(20), default="chapter", comment="分类维度")
    # 图标(emoji)
    icon: Mapped[Optional[str]] = mapped_column(String(10))


class KnowledgeDoc(Base, TimestampMixin):
    """数据资产文档 —— 整个系统的数据基座。

    多源接入：feishu(飞书导入) / crawler(爬虫) / upload(上传) / curl(cURL快速抓取) / manual(手动录入)
    统一归档：按 来源+类型+省份+时间线 组织
    AI处理：自动摘要/关键词/分类/知识点关联
    服务上层：学习刷题/考试预测/交易模拟/AI助手检索

    这是系统最核心的资产——所有上层模块都依赖这里的数据做扩展。
    """
    __tablename__ = "knowledge_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    # 类型：national_policy/regulation/exchange_info/industry_news/exam_info
    doc_type: Mapped[str] = mapped_column(String(30), index=True)
    # 省份：null=全国级
    province: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    region: Mapped[Optional[str]] = mapped_column(String(20), comment="区域如华北/华东")
    grid: Mapped[Optional[str]] = mapped_column(String(10), comment="sgcc/csg/impc")

    # ---- 科学分类体系（主分类树 + 多维标签）----
    # 主分类归属：指向 CategoryNode.code（如311=中长期市场）
    category_code: Mapped[Optional[str]] = mapped_column(String(10), index=True, comment="主分类编码")
    # 多维交叉标签 JSON: {entity:[],product:[],timeframe:[],source:[]}
    # entity: 发电/电网/售电/用户/新型主体
    # product: 中长期/现货/辅助服务/容量/绿电/储能...
    # timeframe: 年度/月度/日前/实时
    facet_tags: Mapped[Optional[str]] = mapped_column(Text, comment="多维标签JSON")

    publish_date: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    doc_number: Mapped[Optional[str]] = mapped_column(String(200), comment="文号")
    source: Mapped[str] = mapped_column(String(100), comment="来源网站名/飞书/上传者")
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))

    # ---- 多源接入（数据资产核心字段）----
    # 数据来源：feishu/crawler/upload/curl/manual
    ingest_type: Mapped[str] = mapped_column(
        String(20), default="manual", index=True,
        comment="feishu飞书导入/crawler爬虫/upload上传/curl快速抓取/manual手动录入"
    )
    # 原始来源元信息 JSON（飞书node_token、爬虫源key、上传文件名等）
    source_meta: Mapped[Optional[str]] = mapped_column(Text)

    # 正文（清洗后的纯文本/摘要）
    content: Mapped[Optional[str]] = mapped_column(Text)
    # AI提炼
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, comment="一段话摘要")
    ai_keywords: Mapped[Optional[str]] = mapped_column(Text, comment="JSON关键词数组")
    ai_interpreted: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_category: Mapped[Optional[str]] = mapped_column(String(50), comment="AI自动归类")

    # 关联：政策→知识点（自动关联）
    knowledge_point_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("knowledge_points.id"), index=True
    )
    # 标签
    tags: Mapped[Optional[str]] = mapped_column(Text, comment="JSON标签数组")

    # 阅读统计
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否收藏")

    # 运维：审核状态（外部数据进库待审核）
    review_status: Mapped[str] = mapped_column(
        String(20), default="approved", index=True,
        comment="approved已过审/pending待审核/rejected驳回/draft草稿"
    )
    # 运维：数据质量分（0-100，系统自动评估）
    quality_score: Mapped[Optional[int]] = mapped_column(Integer, comment="质量评分0-100")
    # 运维：被引用次数（AI助手召回/题目关联/规则引用各+1）
    ref_count: Mapped[int] = mapped_column(Integer, default=0, comment="被上层引用次数")
    # 运维：是否过期（政策有时效）
    is_outdated: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已过期")

    # 去重
    dedup_key: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)

    # 附件（下载的PDF/Word等）
    attachments: Mapped[list["AssetAttachment"]] = relationship(
        back_populates="doc", cascade="all, delete-orphan"
    )


class AssetAttachment(Base, TimestampMixin):
    """数据资产附件 —— 下载的PDF/Word/Excel等文件。"""
    __tablename__ = "asset_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("knowledge_docs.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    file_type: Mapped[str] = mapped_column(String(20), comment="pdf/doc/xlsx/mp4...")
    file_url: Mapped[Optional[str]] = mapped_column(String(1000), comment="原始URL")
    local_path: Mapped[Optional[str]] = mapped_column(String(500), comment="本地存储路径")
    file_size: Mapped[Optional[int]] = mapped_column(Integer, comment="字节数")

    doc: Mapped["KnowledgeDoc"] = relationship(back_populates="attachments")


class DocChunk(Base, TimestampMixin):
    """文档分块 —— 向量知识库的核心。

    每篇 KnowledgeDoc 被切分成多个 chunk，每个 chunk 向量化后存入，
    支撑语义检索召回（AI助手问答、知识关联、规则检索）。

    向量存储策略：
    - embedding 字段存 JSON 序列化的 float 数组（SQLite友好）
    - 索引时全量加载到内存做余弦相似度（万级chunk毫秒级）
    - 扩展时可换 FAISS/Milvus
    """
    __tablename__ = "doc_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("knowledge_docs.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, comment="分块序号")
    text: Mapped[str] = mapped_column(Text, comment="分块文本")

    # 向量（JSON float数组，如 [0.12, -0.03, ...]）
    embedding: Mapped[Optional[str]] = mapped_column(Text, comment="向量JSON")
    embedding_model: Mapped[Optional[str]] = mapped_column(String(50), comment="向量化用的模型名")
    chunk_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True, comment="文本hash去重")

    # 继承父文档的维度（便于过滤召回）
    doc_type: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    province: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    knowledge_point_id: Mapped[Optional[int]] = mapped_column(ForeignKey("knowledge_points.id"), index=True)


class PublicData(Base, TimestampMixin):
    """公共数据 —— 结构化时序数据（出清价/负荷/煤价/碳价）。

    与文档型知识不同，这里存数值型数据，支撑数据分析和交易模拟。
    """
    __tablename__ = "public_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_type: Mapped[str] = mapped_column(String(30), index=True, comment="clearing/coal/carbon/load/renewable")
    province: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    # 数据日期/时间
    data_date: Mapped[str] = mapped_column(String(20), index=True, comment="YYYY-MM-DD 或 YYYY-MM-DD HH:MM")
    # 指标键值对 JSON: {"clearing_price":315.5, "load":12000, ...}
    metrics: Mapped[str] = mapped_column(Text, comment="JSON指标")
    source: Mapped[Optional[str]] = mapped_column(String(100))
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    provenance_level: Mapped[str] = mapped_column(
        String(30), default="synthetic", index=True,
        comment="observed_public/observed_authorized/reconstructed/synthetic",
    )
    disclosure_scope: Mapped[str] = mapped_column(
        String(30), default="public", comment="public/member/specific/private"
    )
    fetched_at: Mapped[Optional[str]] = mapped_column(String(40))
    raw_asset_path: Mapped[Optional[str]] = mapped_column(String(1000))
    raw_sha256: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    parser_version: Mapped[Optional[str]] = mapped_column(String(50))
    quality_status: Mapped[str] = mapped_column(
        String(20), default="unknown", index=True, comment="valid/suspect/invalid/unknown"
    )
    dedup_key: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)


class CrawlSourceItem(Base, TimestampMixin):
    """外部原文采集账本 —— 在请求详情页之前完成增量判断。

    PublicData/Policy 的 dedup_key 负责“不要重复入库”；本表负责更早一层的
    “不要重复下载和解析”。同一站点原文在解析器版本未变化且上次成功时，
    定时任务只扫描列表页，不再请求详情页。
    """
    __tablename__ = "crawl_source_items"
    __table_args__ = (
        UniqueConstraint("crawler_name", "source_item_id", name="uq_crawl_source_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crawler_name: Mapped[str] = mapped_column(String(80), index=True)
    source_item_id: Mapped[str] = mapped_column(
        String(200), index=True, comment="站点文章ID；无显式ID时使用规范化URL哈希"
    )
    source_url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[Optional[str]] = mapped_column(String(500))
    published_at: Mapped[Optional[str]] = mapped_column(
        String(40), comment="列表或原文披露的发布日期，不用抓取时间代替"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="discovered", index=True,
        comment="discovered/success/failed",
    )
    content_sha256: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    parser_version: Mapped[Optional[str]] = mapped_column(String(50))
    data_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error_message: Mapped[Optional[str]] = mapped_column(String(1000))
