"use strict";

const translations = {
  en: {
    title: "Medal standings · Olympic BOINC",
    description: "Olympic-style BOINC team medal standings. Challenge results by year and type.",
    home: "Olympic BOINC — home",
    headerNote: "Team achievements",
    language: "Language",
    eyebrow: "Every podium finish counts",
    heading: "Medal standings",
    introFirst: "Teams that reach the podium.",
    introSecond: "Gold, silver, and bronze from BOINC challenges in one table.",
    results: "Challenge results",
    year: "Year",
    allTime: "All time",
    challengeType: "Challenge type",
    allTypes: "All types",
    teamType: "Team",
    projectType: "Project",
    yearNoteFirst: "Year is based on the challenge",
    yearNoteSecond: "end date in UTC.",
    teamStandings: "Team standings",
    medalTable: "Medal table",
    caption: "Team medals for the selected period and challenge type",
    team: "Team",
    gold: "Gold",
    silver: "Silver",
    bronze: "Bronze",
    total: "Total",
    retry: "Retry",
    tableNote: "Gold first, then silver and bronze — the Olympic system.",
    source: "Challenge results from",
    medalPlaces: "1st place — gold · 2nd — silver · 3rd — bronze",
    loading: "Loading…",
    empty: "No medals for the selected period and challenge type",
    medalsError: "Could not load the medal standings. Please try again.",
    yearsError: "Could not load the year list. Please try again.",
    teamCount: "Teams in standings:",
  },
  ru: {
    title: "Медальный зачёт · Olympic BOINC",
    description: "Олимпийский медальный зачёт команд BOINC. Результаты соревнований по годам и типам.",
    home: "Olympic BOINC — главная",
    headerNote: "Командные достижения",
    language: "Язык",
    eyebrow: "Каждое призовое место имеет значение",
    heading: "Медальный зачёт",
    introFirst: "Команды, которые поднимаются на пьедестал.",
    introSecond: "Золото, серебро и бронза соревнований BOINC в одной таблице.",
    results: "Результаты соревнований",
    year: "Год",
    allTime: "За весь период",
    challengeType: "Тип соревнования",
    allTypes: "Все типы",
    teamType: "Командные",
    projectType: "Проектные",
    yearNoteFirst: "Год определяется по дате",
    yearNoteSecond: "окончания соревнования в UTC.",
    teamStandings: "Командный зачёт",
    medalTable: "Таблица медалей",
    caption: "Медали команд за выбранный период и тип соревнований",
    team: "Команда",
    gold: "Золото",
    silver: "Серебро",
    bronze: "Бронза",
    total: "Всего",
    retry: "Повторить",
    tableNote: "Сначала золото, затем серебро и бронза — по олимпийской системе.",
    source: "Результаты соревнований",
    medalPlaces: "1-е место — золото · 2-е — серебро · 3-е — бронза",
    loading: "Загрузка…",
    empty: "За выбранный период и тип соревнований медалей нет",
    medalsError: "Не удалось загрузить медальный зачёт. Попробуйте ещё раз.",
    yearsError: "Не удалось загрузить список лет. Попробуйте ещё раз.",
    teamCount: "Команд в зачёте:",
  },
};

const languageSelect = document.querySelector("#language");
let language = "en";
let statusKey = "loading";
let displayedTeamCount = null;

function translate(key) {
  return key ? translations[language][key] : "";
}

function translateFeedback() {
  status.textContent = translate(statusKey);
  teamCount.textContent = displayedTeamCount === null ? "" :
    `${translate("teamCount")} ${displayedTeamCount}`;
}

function applyLanguage() {
  document.documentElement.lang = language;
  document.title = translate("title");
  languageSelect.value = language;
  for (const element of document.querySelectorAll("[data-i18n]")) {
    element.textContent = translate(element.dataset.i18n);
  }
  for (const element of document.querySelectorAll("[data-i18n-label]")) {
    element.setAttribute("aria-label", translate(element.dataset.i18nLabel));
  }
  for (const element of document.querySelectorAll("[data-i18n-content]")) {
    element.setAttribute("content", translate(element.dataset.i18nContent));
  }
  translateFeedback();
}

function restoreLanguage() {
  try {
    const saved = localStorage.getItem("olympic-language");
    if (saved === "en" || saved === "ru") language = saved;
  } catch {
    // Storage can be blocked; the page still works with an in-memory choice.
  }
  applyLanguage();
}

function changeLanguage() {
  language = languageSelect.value === "ru" ? "ru" : "en";
  try {
    localStorage.setItem("olympic-language", language);
  } catch {
    // Keep the selected language usable even when it cannot be persisted.
  }
  applyLanguage();
}

const yearSelect = document.querySelector("#year");
const typeSelect = document.querySelector("#challenge-type");
const rows = document.querySelector("#medal-rows");
const status = document.querySelector("#status");
const results = document.querySelector("#results");
const retry = document.querySelector("#retry");
const teamCount = document.querySelector("#team-count");
let yearsLoaded = false;
let requestId = 0;
let controller;

function showStatus(key, loading = false, failed = false) {
  rows.replaceChildren();
  statusKey = key;
  displayedTeamCount = null;
  translateFeedback();
  status.classList.toggle("error", failed);
  results.setAttribute("aria-busy", String(loading));
  retry.hidden = !failed;
}

async function getJSON(url, signal) {
  const response = await fetch(url, { signal, cache: "no-store" });
  if (!response.ok) throw new Error("Request failed");
  return response.json();
}

function renderMedals(data) {
  if (!Array.isArray(data) || !data.every(row =>
    typeof row.team_name === "string" &&
    ["gold", "silver", "bronze", "total"].every(key => Number.isSafeInteger(row[key]) && row[key] >= 0)
  )) throw new Error("Invalid medals response");

  showStatus(data.length ? "" : "empty");
  const fragment = document.createDocumentFragment();
  for (const team of data) {
    const row = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = team.team_name;
    row.append(name);
    for (const key of ["gold", "silver", "bronze", "total"]) {
      const cell = document.createElement("td");
      cell.textContent = String(team[key]);
      if (team[key] === 0) cell.classList.add("zero");
      row.append(cell);
    }
    fragment.append(row);
  }
  rows.replaceChildren(fragment);
  displayedTeamCount = data.length;
  translateFeedback();
}

async function loadStandings() {
  const id = ++requestId;
  controller?.abort();
  controller = new AbortController();
  const { signal } = controller;
  showStatus("loading", true);

  try {
    if (!yearsLoaded) {
      const years = await getJSON("/api/challenges/years", signal);
      if (id !== requestId) return;
      if (!Array.isArray(years) || !years.every(year => Number.isInteger(year) && year >= 1 && year <= 9999)) {
        throw new Error("Invalid years response");
      }
      const allTime = new Option(translate("allTime"), "all");
      allTime.dataset.i18n = "allTime";
      yearSelect.replaceChildren(allTime);
      for (const year of years) yearSelect.add(new Option(String(year), String(year)));
      yearsLoaded = true;
      yearSelect.disabled = false;
      typeSelect.disabled = false;
    }

    const params = new URLSearchParams({ challenge_type: typeSelect.value });
    if (yearSelect.value !== "all") {
      const year = yearSelect.value.padStart(4, "0");
      params.set("from", `${year}-01-01`);
      params.set("to", `${year}-12-31`);
    }
    const data = await getJSON(`/api/medals?${params}`, signal);
    if (id === requestId) renderMedals(data);
  } catch (error) {
    if (id !== requestId || signal.aborted) return;
    showStatus(
      yearsLoaded ? "medalsError" : "yearsError",
      false, true,
    );
  }
}

restoreLanguage();
languageSelect.addEventListener("change", changeLanguage);
yearSelect.addEventListener("change", loadStandings);
typeSelect.addEventListener("change", loadStandings);
retry.addEventListener("click", loadStandings);
loadStandings();
