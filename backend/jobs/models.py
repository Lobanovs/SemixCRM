from __future__ import annotations

from dataclasses import dataclass, field


JOB_SOURCES = ("hh", "habr", "telegram", "remoteok", "remotive", "weworkremotely")

# Каналы проверены запросом к t.me/s/<канал>: у каждого есть публичное превью
# с живой лентой. Названия, которых не существует, в список не попали.
TELEGRAM_JOB_CHANNELS = (
    # Фронтенд и веб
    "forfrontend", "forwebdev", "devsjobs", "devjobs", "webdev_jobs", "wordpress_jobs", "nocode_jobs",
    # Общие IT-вакансии
    "itjobs_ru", "it_hunters", "itmozg", "proglib_jobs", "tproger_official", "habr_career",
    "careerspace", "jobforjunior", "itmatch", "itstartupjobs",
    # Удалёнка и валюта
    "remote_it_jobs", "remoteit", "remotejobs", "nomadjobs", "jobs_abroad", "relocateme",
    # Смежные направления
    "devops_jobs_feed", "java_jobs_ru", "kotlin_jobs", "gamedevjob", "designhunters",
    "product_jobs", "startup_jobs",
    # Прямые работодатели
    "ozon_jobs", "avito_jobs",
)
JOB_STATUSES = ("Сохранено", "Откликнулся", "Ответили", "Собеседование", "Оффер", "Отказ")

JOB_NEXT_STEPS = {
    "Сохранено": "Изучить и откликнуться",
    "Откликнулся": "Жду ответа",
    "Ответили": "Договориться о созвоне",
    "Собеседование": "Подготовиться к интервью",
    "Оффер": "Обсудить условия",
    "Отказ": "Вернуться позже",
}

# Города, для которых hh.ru использует собственные идентификаторы регионов.
HH_AREAS = {
    "россия": "113",
    "москва": "1",
    "санкт-петербург": "2",
    "спб": "2",
    "питер": "2",
    "новосибирск": "4",
    "екатеринбург": "3",
    "казань": "88",
    "краснодар": "53",
    "нижний новгород": "66",
    "ростов-на-дону": "76",
    "самара": "78",
    "воронеж": "26",
    "уфа": "99",
    "пермь": "72",
    "красноярск": "54",
    "сочи": "237",
}


@dataclass(frozen=True)
class JobVacancy:
    source: str
    external_id: str
    company: str
    role: str
    description: str = ""
    url: str = ""
    tags: tuple[str, ...] = ()
    salary_min: int | None = None
    salary_max: int | None = None
    currency: str = "RUB"
    salary_text: str = ""
    location: str = ""
    employment: str = ""
    published_at: str = ""
    discovered_at: str = ""

    def validated(self) -> "JobVacancy":
        if not self.role.strip():
            raise ValueError("У вакансии должно быть название")
        return self


@dataclass(frozen=True)
class JobSettings:
    sources: tuple[str, ...] = JOB_SOURCES
    keywords: tuple[str, ...] = ("react", "typescript", "frontend", "next.js")
    excluded_keywords: tuple[str, ...] = ("стажёр", "неоплачиваемая")
    telegram_channels: tuple[str, ...] = TELEGRAM_JOB_CHANNELS
    area: str = "Россия"
    salary_min: int = 0
    remote_only: bool = False
    per_source_limit: int = 50

    def hh_area(self) -> str:
        return HH_AREAS.get(self.area.strip().lower(), "113")


@dataclass(frozen=True)
class JobAdapterResult:
    source: str
    status: str = "done"
    vacancies: tuple[JobVacancy, ...] = ()
    checked_at: str = ""
    error: str = ""


@dataclass
class JobParseRun:
    """Состояние фонового сбора вакансий, которое опрашивает интерфейс."""

    id: str
    sources: list[str]
    status: str = "pending"
    message: str = "Подготовка парсера вакансий"
    error: str = ""
    inserted: int = 0
    duplicates: int = 0
    source_states: dict[str, dict[str, object]] = field(default_factory=dict)

    def snapshot(self) -> dict[str, object]:
        return {
            "run_id": self.id,
            "status": self.status,
            "message": self.message,
            "error": self.error,
            "inserted": self.inserted,
            "duplicates": self.duplicates,
            "sources": self.source_states,
        }
