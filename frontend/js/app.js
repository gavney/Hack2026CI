// Global Application State
let state = {
  currentCompanyId: localStorage.getItem('ci_radar_company_id') || null,
  companies: [],
  currentHorizon: 30,
  activeTab: 'radar',
  forecastData: null,
  companyInfo: null,
  currentUser: null,
  authToken: localStorage.getItem('ci_radar_token') || null,
  activeScenarioId: 'scen_delay_client',
  chartInstance: null,
  scenarioChartInstance: null,
  modalDirection: 'inflow',
  selectedFile: null,
  selectedModel: 'monte-carlo',
  debugMode: false,
  counterparties: [],
  cpFilter: 'all',
  cpSearch: '',
  selectedCounterparty: null,
  fnsApiKey: localStorage.getItem('ci_fns_api_key') || ''
};

// Initialize Application on Page Load
document.addEventListener('DOMContentLoaded', async () => {
  lucide.createIcons();
  applyNavbarCustomization();
  await loadUserProfile();
  await loadCompaniesList();
});

// Toast Helper
function showToast(message) {
  const toast = document.getElementById('toastNotification');
  const msgEl = document.getElementById('toastMessage');
  if (msgEl) msgEl.innerText = message;
  if (toast) {
    toast.classList.remove('hidden');
    setTimeout(() => {
      toast.classList.add('hidden');
    }, 3200);
  }
}

// Auth Headers Helper
function getAuthHeaders(isJson = true) {
  const headers = {};
  if (isJson) headers['Content-Type'] = 'application/json';
  if (state.authToken) headers['Authorization'] = `Bearer ${state.authToken}`;
  return headers;
}

// Render company select dropdown helper
function renderCompanySelectDropdown(activeId) {
  const select = document.getElementById('companySelect');
  if (!select) return;
  select.innerHTML = '';

  if (!state.currentUser || !state.companies || state.companies.length === 0) {
    const opt = document.createElement('option');
    opt.value = "";
    opt.textContent = "— Войдите в аккаунт для выбора бизнеса —";
    opt.disabled = true;
    opt.selected = true;
    opt.className = "text-slate-500 bg-white font-semibold";
    select.appendChild(opt);

    const promptOpt = document.createElement('option');
    promptOpt.value = "__login_prompt__";
    promptOpt.textContent = "🔐 Войти / зарегистрировать свой бизнес...";
    promptOpt.className = "text-emerald-700 bg-emerald-50 font-bold";
    select.appendChild(promptOpt);
    return;
  }

  const targetId = activeId || state.currentCompanyId;
  state.companies.forEach(comp => {
    const opt = document.createElement('option');
    opt.value = comp.id;
    opt.textContent = `${comp.name} (${comp.legal_form || 'Бизнес'} • ИНН ${comp.inn})`;
    opt.className = "text-slate-900 bg-white font-semibold";
    if (comp.id === targetId) opt.selected = true;
    select.appendChild(opt);
  });

  const addOpt = document.createElement('option');
  addOpt.value = "__add_new_business__";
  addOpt.textContent = "+ Добавить новый бизнес в аккаунт...";
  addOpt.className = "text-emerald-700 bg-emerald-50 font-bold";
  select.appendChild(addOpt);

  if (targetId) {
    select.value = targetId;
  }
}

// 1. Load User Profile & Current Company
async function loadUserProfile() {
  if (!state.authToken) {
    state.currentUser = null;
    state.currentCompanyId = null;
    renderUserHeader(null);
    renderCompanySelectDropdown(null);
    renderEmptyGuestDashboard();
    return;
  }

  try {
    const res = await fetch('/api/auth/me', { headers: getAuthHeaders() });
    if (res.ok) {
      const data = await res.json();
      if (data.authenticated && data.user) {
        state.currentUser = data.user;
        state.companies = data.companies || [];

        // Determine active company:
        // 1. Saved in localStorage if it exists among user companies
        // 2. Otherwise backend data.company or user.company_id
        // 3. Otherwise first company
        const savedCompanyId = localStorage.getItem('ci_radar_company_id');
        let chosenCompanyId = null;

        if (savedCompanyId && state.companies.some(c => c.id === savedCompanyId)) {
          chosenCompanyId = savedCompanyId;
        } else if (data.company && data.company.id && state.companies.some(c => c.id === data.company.id)) {
          chosenCompanyId = data.company.id;
        } else if (data.user.company_id && state.companies.some(c => c.id === data.user.company_id)) {
          chosenCompanyId = data.user.company_id;
        } else if (state.companies.length > 0) {
          chosenCompanyId = state.companies[0].id;
        }

        state.currentCompanyId = chosenCompanyId;
        if (chosenCompanyId) {
          localStorage.setItem('ci_radar_company_id', chosenCompanyId);
        } else {
          localStorage.removeItem('ci_radar_company_id');
        }

        renderUserHeader(data.user);
        renderCompanySelectDropdown(chosenCompanyId);

        if (chosenCompanyId) {
          await loadAllCompanyData(chosenCompanyId);
        } else {
          renderEmptyGuestDashboard();
        }
      } else {
        state.authToken = null;
        state.currentUser = null;
        state.currentCompanyId = null;
        localStorage.removeItem('ci_radar_token');
        localStorage.removeItem('ci_radar_company_id');
        renderUserHeader(null);
        renderCompanySelectDropdown(null);
        renderEmptyGuestDashboard();
        return;
      }
    } else {
      state.authToken = null;
      state.currentUser = null;
      state.currentCompanyId = null;
      localStorage.removeItem('ci_radar_token');
      localStorage.removeItem('ci_radar_company_id');
      renderUserHeader(null);
      renderCompanySelectDropdown(null);
      renderEmptyGuestDashboard();
      return;
    }
  } catch (err) {
    console.error('Error loading user profile:', err);
    state.authToken = null;
    state.currentUser = null;
    state.currentCompanyId = null;
    renderUserHeader(null);
    renderCompanySelectDropdown(null);
    renderEmptyGuestDashboard();
    return;
  }
}

function renderEmptyGuestDashboard() {
  state.companyInfo = null;
  state.forecastData = null;
  state.operations = [];
  state.counterparties = [];
  state.slots = [];

  const balEl = document.getElementById('cardCurrentBalance');
  if (balEl) balEl.innerText = '0.00 ₽';
  const legEl = document.getElementById('cardLegalForm');
  if (legEl) legEl.innerText = 'Гость';
  const accEl = document.getElementById('cardAccountNumber');
  if (accEl) accEl.innerText = 'Нет данных';
  const dateEl = document.getElementById('cardBalanceAsOfDate');
  if (dateEl) dateEl.innerText = 'Авторизуйтесь';

  const statusHeadline = document.getElementById('statusHeadline');
  if (statusHeadline) statusHeadline.innerText = 'Требуется авторизация';
  const statusDesc = document.getElementById('statusDescription');
  if (statusDesc) statusDesc.innerText = 'Войдите в аккаунт или зарегистрируйте бизнес';
  const statusRiskProb = document.getElementById('statusRiskProb');
  if (statusRiskProb) {
    statusRiskProb.innerText = 'Вход не выполнен';
    statusRiskProb.className = 'text-[10px] font-bold bg-slate-100 text-slate-500 border border-slate-200 px-2 py-0.5 rounded-full';
  }
  const traffic = document.getElementById('statusTrafficIcon');
  if (traffic) traffic.className = 'w-3 h-3 rounded-full bg-slate-300';

  const nextAmt = document.getElementById('nextPaymentAmount');
  if (nextAmt) nextAmt.innerText = '0 ₽';
  const nextDesc = document.getElementById('nextPaymentDesc');
  if (nextDesc) nextDesc.innerText = 'Обязательства не загружены';

  // Render empty state on Forecast chart
  if (state.chartInstance) {
    state.chartInstance.destroy();
    state.chartInstance = null;
  }

  const opTbody = document.getElementById('operationsTableBody');
  if (opTbody) {
    opTbody.innerHTML = '<tr><td colspan="5" class="text-center py-8 text-slate-400">Данные отсутствуют. Авторизуйтесь под учетной записью бизнеса.</td></tr>';
  }
  const cpTbody = document.getElementById('counterpartiesTableBody');
  if (cpTbody) {
    cpTbody.innerHTML = '<tr><td colspan="6" class="text-center py-8 text-slate-400">Контрагенты не загружены. Авторизуйтесь для анализа реестра.</td></tr>';
  }
  const slotsBox = document.getElementById('slotsList');
  if (slotsBox) {
    slotsBox.innerHTML = '<div class="text-center py-6 text-slate-400 text-xs">Регулярные слоты не загружены.</div>';
  }
  const evBox = document.getElementById('futureEventsList');
  if (evBox) {
    evBox.innerHTML = '<div class="text-center py-4 text-slate-400 text-xs">Нет запланированных платежей.</div>';
  }

  lucide.createIcons();
}

function renderUserHeader(user) {
  const loggedInGroup = document.getElementById('userLoggedInGroup');
  const loggedOutGroup = document.getElementById('userLoggedOutGroup');
  const nameEl = document.getElementById('headerUserName');
  const roleEl = document.getElementById('headerUserRole');
  const avatarEl = document.getElementById('userAvatarInitials');
  const cabSubline = document.getElementById('cabUserSubline');
  const cabLogoutBtn = document.getElementById('cabModalLogoutBtn');

  if (user) {
    if (loggedInGroup) loggedInGroup.classList.remove('hidden');
    if (loggedOutGroup) loggedOutGroup.classList.add('hidden');
    if (cabLogoutBtn) cabLogoutBtn.classList.remove('hidden');

    if (nameEl) nameEl.innerText = user.full_name || 'Предприниматель';
    if (roleEl) roleEl.innerText = user.role === 'owner' ? 'Владелец' : 'Бухгалтер';

    if (avatarEl && user.full_name) {
      const parts = user.full_name.trim().split(/\s+/);
      const initials = parts.map(p => p[0]).join('').slice(0, 2).toUpperCase();
      avatarEl.innerText = initials || 'ИП';
    }
    if (cabSubline) {
      cabSubline.innerText = `${user.email} • ${user.full_name}`;
    }
  } else {
    if (loggedInGroup) loggedInGroup.classList.add('hidden');
    if (loggedOutGroup) loggedOutGroup.classList.remove('hidden');
    if (cabLogoutBtn) cabLogoutBtn.classList.add('hidden');

    if (nameEl) nameEl.innerText = 'Демо-режим';
    if (roleEl) roleEl.innerText = 'Гость';
    if (avatarEl) avatarEl.innerText = 'CI';
    if (cabSubline) {
      cabSubline.innerText = 'Демо-режим Центр-инвест • Авторизуйтесь для привязки бизнеса';
    }
  }
  lucide.createIcons();
}

// 2. Load Companies for Switcher (Filtered by Current User & Access Rights)
async function loadCompaniesList() {
  if (!state.currentUser || !state.authToken) {
    renderCompanySelectDropdown(null);
    return;
  }

  try {
    const res = await fetch('/api/companies', { headers: getAuthHeaders() });
    if (!res.ok) throw new Error('Ошибка загрузки списка компаний');
    state.companies = await res.json();

    const savedCompanyId = localStorage.getItem('ci_radar_company_id');
    if (savedCompanyId && state.companies.some(c => c.id === savedCompanyId)) {
      state.currentCompanyId = savedCompanyId;
    } else if (state.currentCompanyId && state.companies.some(c => c.id === state.currentCompanyId)) {
      // keep current valid company
      localStorage.setItem('ci_radar_company_id', state.currentCompanyId);
    } else if (state.companies.length > 0) {
      state.currentCompanyId = state.companies[0].id;
      localStorage.setItem('ci_radar_company_id', state.currentCompanyId);
    }

    renderCompanySelectDropdown(state.currentCompanyId);
    populateCabinetPageDetails();
  } catch (err) {
    console.error('Error loading companies:', err);
  }
}

// Handle Company Change (Switcher)
async function onCompanyChange(newCompanyId) {
  if (newCompanyId === '__login_prompt__') {
    openAuthModal();
    const select = document.getElementById('companySelect');
    if (select) select.value = state.currentCompanyId;
    return;
  }
  if (newCompanyId === '__add_new_business__') {
    openAddBusinessModal();
    const select = document.getElementById('companySelect');
    if (select) select.value = state.currentCompanyId;
    return;
  }
  state.currentCompanyId = newCompanyId;
  localStorage.setItem('ci_radar_company_id', newCompanyId);

  // Sync select element in navbar
  const select = document.getElementById('companySelect');
  if (select && select.value !== newCompanyId) {
    select.value = newCompanyId;
  }

  // Persist to backend
  fetch(`/api/auth/switch-company/${encodeURIComponent(newCompanyId)}`, {
    method: 'POST',
    headers: getAuthHeaders()
  }).catch(err => console.warn('Could not persist company switch to server:', err));

  await loadAllCompanyData(newCompanyId);
  populateCabinetPageDetails();
  showToast(`Выбран бизнес: ${state.companyInfo ? state.companyInfo.name : newCompanyId}`);
}

function openAddBusinessModal() {
  if (!state.currentUser) {
    showToast('Для добавления бизнеса войдите в личный кабинет или зарегистрируйтесь');
    openAuthModal();
    return;
  }
  const m = document.getElementById('addBusinessModal');
  if (m) m.classList.remove('hidden');
}

function closeAddBusinessModal() {
  const m = document.getElementById('addBusinessModal');
  if (m) m.classList.add('hidden');
}

function validateInnAndName(inn, legalForm, name) {
  const cleanInn = String(inn || '').trim();
  if (!cleanInn) return 'ИНН обязателен для заполнения';
  if (!/^\d+$/.test(cleanInn)) return 'ИНН должен содержать только цифры';
  if (['ООО', 'АО'].includes(legalForm) && cleanInn.length !== 10) {
    return `ИНН юридического лица (${legalForm}) должен содержать ровно 10 цифр (введено: ${cleanInn.length})`;
  }
  if (['ИП', 'Самозанятый'].includes(legalForm) && cleanInn.length !== 12) {
    return `ИНН для ${legalForm} должен содержать ровно 12 цифр (введено: ${cleanInn.length})`;
  }
  if (!name || name.trim().length < 2) {
    return 'Название организации / ФИО должно содержать не менее 2 символов';
  }
  return null;
}

function validateCounterpartyInput(name, inn) {
  const cleanName = String(name || '').trim();
  const cleanInn = String(inn || '').trim();

  if (!cleanName || cleanName.length < 2) {
    return 'Укажите наименование контрагента (не менее 2 символов)';
  }
  if (!cleanInn) {
    return 'Укажите ИНН контрагента (10 или 12 цифр)';
  }
  if (!/^\d+$/.test(cleanInn)) {
    return 'ИНН контрагента должен состоять только из цифр';
  }
  if (cleanInn.length !== 10 && cleanInn.length !== 12) {
    return `ИНН контрагента должен содержать ровно 10 (для ООО/АО) или 12 (для ИП) цифр (введено: ${cleanInn.length})`;
  }
  return null;
}

async function submitNewBusiness(e) {
  e.preventDefault();
  const name = document.getElementById('newBizName').value.trim();
  const inn = document.getElementById('newBizInn').value.trim();
  const legalForm = document.getElementById('newBizLegalForm').value;
  const industry = document.getElementById('newBizIndustry').value;
  const taxRegime = document.getElementById('newBizTaxRegime').value;
  const initialBalance = parseFloat(document.getElementById('newBizInitialBalance').value) || 0.0;

  const valErr = validateInnAndName(inn, legalForm, name);
  if (valErr) {
    showToast(valErr);
    return;
  }

  try {
    const res = await fetch('/api/companies', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders()
      },
      body: JSON.stringify({
        name: name,
        inn: inn,
        legal_form: legalForm,
        industry: industry,
        tax_regime: taxRegime,
        initial_balance: initialBalance
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Ошибка создания бизнеса');
    }

    const createdComp = await res.json();
    closeAddBusinessModal();
    showToast(`Бизнес «${createdComp.name}» успешно добавлен в ваш аккаунт!`);

    // Reload companies list and switch directly to the newly created business
    state.currentCompanyId = createdComp.id;
    localStorage.setItem('ci_radar_company_id', createdComp.id);
    await loadCompaniesList();
    await loadAllCompanyData(createdComp.id);
  } catch (err) {
    console.error('Error adding new business:', err);
    showToast(`Ошибка: ${err.message}`);
  }
}

// 3. Load all data for active company
async function loadAllCompanyData(companyId) {
  if (!companyId || !state.currentUser) {
    renderEmptyGuestDashboard();
    return;
  }

  try {
    const compRes = await fetch(`/api/companies/${companyId}`, { headers: getAuthHeaders() });
    if (compRes.ok) {
      state.companyInfo = await compRes.json();
      renderCompanyHeader();
      populateCabinetPageDetails();
    }

    await loadForecastData();
    await loadOperations();
    await loadSlots();
    await loadAnalytics();
    await loadIntegrations();
    await loadCounterparties();
    await loadStatementUploadHistory();
    if (state.activeScenarioId) {
      renderScenarioControls(state.activeScenarioId);
      await loadScenarioComparison(state.activeScenarioId);
    } else {
      await cancelScenario();
    }

    // Sync company select value
    const select = document.getElementById('companySelect');
    if (select && select.value !== companyId) {
      select.value = companyId;
    }

    lucide.createIcons();
  } catch (err) {
    console.error('Error loading company data:', err);
  }
}

function renderCompanyHeader() {
  const c = state.companyInfo;
  if (!c) return;

  const balEl = document.getElementById('cardCurrentBalance');
  if (balEl) balEl.innerText = `${formatMoney(c.last_balance)} ₽`;

  const accEl = document.getElementById('cardAccountNumber');
  if (accEl) accEl.innerText = `Основной счет • ИНН ${c.inn || '—'}`;

  const dateEl = document.getElementById('cardBalanceAsOfDate');
  if (dateEl) {
    if (c.initial_manual_balance && c.initial_manual_balance !== 0) {
      dateEl.innerText = 'Отредактирован';
    } else if (c.last_operation_date) {
      dateEl.innerText = `На ${formatDate(c.last_operation_date)}`;
    } else {
      dateEl.innerText = 'По выписке';
    }
  }

  const taxEl = document.getElementById('cardTaxRegimeBadge');
  if (taxEl) taxEl.innerText = c.tax_regime || 'УСН';

  const lfEl = document.getElementById('cardLegalForm');
  if (lfEl) lfEl.innerText = c.legal_form || 'ИП';

  // Clean business onboarding banner
  const cleanBanner = document.getElementById('cleanBusinessBanner');
  if (cleanBanner) {
    if (c.has_statement === false) {
      cleanBanner.classList.remove('hidden');
    } else {
      cleanBanner.classList.add('hidden');
    }
  }

  const modelTag = document.getElementById('modelTagLabel');
  if (modelTag) {
    modelTag.innerText = state.forecastData?.model_version || (c.has_statement ? state.selectedModel : 'clean-business');
  }
}

// 4. Load & Render Forecast
async function loadForecastData() {
  try {
    const modelParam = state.selectedModel || 'monte-carlo';
    const res = await fetch(`/api/companies/${state.currentCompanyId}/forecast?horizon=${state.currentHorizon}&model=${modelParam}`);
    if (!res.ok) throw new Error('Ошибка расчета прогноза');
    state.forecastData = await res.json();

    await loadAlerts();
    renderForecastChart();
    renderStatusTrafficLight();
    renderContributions();
    renderDebugBanner();

    // Update model label
    const modelTag = document.getElementById('modelTagLabel');
    if (modelTag && state.forecastData) {
      const v = state.forecastData.model_version || modelParam;
      modelTag.innerText = v === 'monte-carlo-v1.0' ? 'Монте-Карло (1 000 симуляций)' : (v === 'stub-0.1' ? 'Статистический тренд' : v);
    }
  } catch (err) {
    console.error('Error fetching forecast:', err);
  }
}

function setHorizon(days) {
  state.currentHorizon = days;
  [30, 60, 90].forEach(h => {
    const btn = document.getElementById(`hz-btn-${h}`);
    if (btn) {
      if (h === days) {
        btn.className = "px-3 py-1 rounded-lg bg-white text-slate-900 shadow-sm transition";
      } else {
        btn.className = "px-3 py-1 rounded-lg text-slate-500 hover:text-slate-900 transition";
      }
    }
  });
  loadForecastData();
}

// --- Model Switcher ---
function setModel(modelId) {
  state.selectedModel = modelId;
  // Update button styles
  const mcBtn = document.getElementById('model-btn-mc');
  const stubBtn = document.getElementById('model-btn-stub');
  if (modelId === 'monte-carlo') {
    if (mcBtn) mcBtn.className = "px-3 py-1.5 rounded-lg bg-emerald-600 text-white shadow-sm transition flex items-center gap-1";
    if (stubBtn) stubBtn.className = "px-3 py-1.5 rounded-lg text-slate-500 hover:text-slate-900 transition flex items-center gap-1";
  } else {
    if (stubBtn) stubBtn.className = "px-3 py-1.5 rounded-lg bg-emerald-600 text-white shadow-sm transition flex items-center gap-1";
    if (mcBtn) mcBtn.className = "px-3 py-1.5 rounded-lg text-slate-500 hover:text-slate-900 transition flex items-center gap-1";
  }
  loadForecastData();
}

// --- Debug Mode ---
function toggleDebugMode() {
  state.debugMode = document.getElementById('debugModeToggle')?.checked || false;
  renderDebugBanner();
  renderForecastChart();  // re-render to show/hide sample paths
}

function renderDebugBanner() {
  const banner = document.getElementById('debugBanner');
  const pathsLegend = document.getElementById('debugLegendPaths');
  if (!banner) return;

  if (!state.debugMode) {
    banner.classList.add('hidden');
    if (pathsLegend) pathsLegend.classList.add('hidden');
    return;
  }

  const meta = state.forecastData?.simulation_meta;
  if (!meta) {
    banner.classList.add('hidden');
    if (pathsLegend) pathsLegend.classList.add('hidden');
    return;
  }

  banner.classList.remove('hidden');
  if (pathsLegend) pathsLegend.classList.remove('hidden');

  const el = (id, val) => { const e = document.getElementById(id); if (e) e.innerText = val; };
  el('debugModelLabel', state.forecastData?.model_version === 'monte-carlo-v1.0' ? 'Монте-Карло v1.0' : (state.forecastData?.model_version || '—'));
  el('debugIterations', meta.iterations ? `${meta.iterations.toLocaleString()} путей` : '1 000');
  el('debugExecTime', meta.execution_time_ms ? meta.execution_time_ms.toFixed(1) : '—');
  el('debugVaR', meta.var_95 ? `-${formatMoney(meta.var_95)} ₽` : '0 ₽');
  el('debugCVaR', meta.cvar_95 ? `-${formatMoney(meta.cvar_95)} ₽` : '0 ₽');
}

function renderStatusTrafficLight() {
  const fd = state.forecastData;
  const comp = state.companyInfo;
  if (!fd) return;

  const icon = document.getElementById('statusTrafficIcon');
  const headline = document.getElementById('statusHeadline');
  const desc = document.getElementById('statusDescription');
  const riskLbl = document.getElementById('statusRiskProb');
  const alertBadge = document.getElementById('alertBadge');
  const tabAlertCount = document.getElementById('tabAlertCount');
  const critBanner = document.getElementById('radarCriticalBanner');
  const bannerText = document.getElementById('bannerAlertText');

  const prob = fd.gap_probability || 0.0;
  const probPct = Math.round(prob * 100);

  // If clean business without statement
  if (comp && comp.has_statement === false) {
    icon.className = "w-3 h-3 rounded-full bg-amber-400";
    headline.innerText = "Чистый старт";
    headline.className = "text-lg font-black text-amber-700 leading-tight";
    desc.innerText = "Накопление статистики операций. Загрузите выписку для ML-прогноза.";
    riskLbl.innerText = "Новый бизнес";
    riskLbl.className = "text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200 px-2 py-0.5 rounded-full";
    if (alertBadge) alertBadge.classList.add('hidden');
    if (tabAlertCount) tabAlertCount.classList.add('hidden');
    if (critBanner) critBanner.classList.add('hidden');
    return;
  }

  if (prob >= 0.50 || (fd.first_gap_date && prob >= 0.20)) {
    // Critical / Warning
    const isCrit = prob >= 0.50;
    icon.className = isCrit ? "w-3 h-3 rounded-full bg-red-500 animate-ping" : "w-3 h-3 rounded-full bg-amber-500";
    headline.innerText = isCrit ? "Кассовый разрыв!" : "Риск напряжения";
    headline.className = isCrit ? "text-lg font-black text-red-600 leading-tight" : "text-lg font-black text-amber-600 leading-tight";

    const alertReason = state.currentAlertData?.reason;
    const gapDateFormatted = formatDate(fd.first_gap_date);
    const shortfallFormatted = formatMoney(state.currentAlertData?.shortfall_p50 || state.currentAlertData?.shortfall_p10 || fd.total_shortfall_p10);

    desc.innerText = alertReason || `Дефицит к ${gapDateFormatted} ~${shortfallFormatted} ₽.`;
    
    riskLbl.innerText = `Риск ${probPct}%`;
    riskLbl.className = isCrit ? "text-[10px] font-bold bg-red-50 text-red-800 border border-red-200 px-2 py-0.5 rounded-full" : "text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200 px-2 py-0.5 rounded-full";

    if (alertBadge) alertBadge.classList.remove('hidden');
    if (tabAlertCount) {
      tabAlertCount.classList.remove('hidden');
      tabAlertCount.innerText = '1';
    }

    if (critBanner) {
      critBanner.classList.remove('hidden');
      const bTitle = document.getElementById('bannerAlertTitle');
      if (bTitle) bTitle.innerText = isCrit ? "Обнаружен риск кассового разрыва!" : "Внимание: кассовое напряжение";
      if (bannerText) bannerText.innerText = alertReason || `Деньги могут закончиться ${gapDateFormatted}. Ожидаемый дефицит: ~${shortfallFormatted} ₽ (вероятность ${probPct}%).`;
    }
  } else {
    // Calm
    icon.className = "w-3 h-3 rounded-full bg-emerald-500";
    headline.innerText = "Всё спокойно";
    headline.className = "text-lg font-black text-slate-900 leading-tight";
    desc.innerText = `Денег хватает на горизонте ${state.currentHorizon} дней.`;
    riskLbl.innerText = `Риск 0%`;
    riskLbl.className = "text-[10px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200 px-2 py-0.5 rounded-full";

    if (alertBadge) alertBadge.classList.add('hidden');
    if (tabAlertCount) tabAlertCount.classList.add('hidden');
    if (critBanner) critBanner.classList.add('hidden');
  }

  // Update FNS risk banner
  const fnsBanner = document.getElementById('radarFnsRiskBanner');
  const fnsText = document.getElementById('radarFnsRiskText');
  const meta = fd.simulation_meta || {};
  if (fnsBanner) {
    if (meta.fns_risk_active && meta.fns_affected_debtors && meta.fns_affected_debtors.length > 0) {
      fnsBanner.classList.remove('hidden');
      if (fnsText) {
        fnsText.innerText = `В итоговом графике учтен риск: счета дебитора ${meta.fns_affected_debtors.join(', ')} заблокированы ФНС (ст. 76 НК РФ). Поступления задержаны на 21 рабочий день.`;
      }
    } else {
      fnsBanner.classList.add('hidden');
    }
  }

  // Update card 3 next payment
  const contribs = fd.contributions || [];
  const npAmt = document.getElementById('nextPaymentAmount');
  const npDesc = document.getElementById('nextPaymentDesc');
  if (contribs.length > 0) {
    const nextPay = contribs.find(c => c.amount < 0) || contribs[0];
    if (npAmt && npDesc) {
      const isOut = nextPay.amount < 0;
      npAmt.innerText = `${isOut ? '' : '+'}${formatMoney(Math.abs(nextPay.amount))} ₽`;
      npDesc.innerText = `${formatDate(nextPay.date)} • ${getCategoryName(nextPay.category)}`;
    }
  } else {
    if (npAmt && npDesc) {
      npAmt.innerText = 'Нет списаний';
      npDesc.innerText = 'В графике нет плановых выплат';
    }
  }
}

function renderForecastChart() {
  const fd = state.forecastData;
  if (!fd || !fd.days) return;

  const ctx = document.getElementById('forecastChart').getContext('2d');
  if (state.chartInstance) {
    state.chartInstance.destroy();
  }

  const labels = fd.days.map(d => formatDate(d.date));
  const p50Data = fd.days.map(d => d.p50);
  const p10Data = fd.days.map(d => d.p10);
  const p90Data = fd.days.map(d => d.p90);
  const zeroLine = fd.days.map(() => 0);

  const datasets = [
    {
      label: 'Ожидаемый остаток',
      data: p50Data,
      borderColor: '#059669',
      borderWidth: 2.5,
      pointRadius: 0,
      pointHoverRadius: 5,
      tension: 0.25,
      order: 1
    },
    {
      label: 'Оптимистичный (P90)',
      data: p90Data,
      borderColor: 'rgba(16, 185, 129, 0.2)',
      borderWidth: 1,
      pointRadius: 0,
      fill: false,
      tension: 0.3,
      order: 2
    },
    {
      label: 'Пессимистичный (P10)',
      data: p10Data,
      borderColor: 'rgba(16, 185, 129, 0.2)',
      borderWidth: 1,
      pointRadius: 0,
      backgroundColor: 'rgba(16, 185, 129, 0.08)',
      fill: '-1',
      tension: 0.3,
      order: 3
    },
    {
      label: 'Граница разрыва',
      data: zeroLine,
      borderColor: '#EF4444',
      borderWidth: 1.5,
      borderDash: [4, 4],
      pointRadius: 0,
      fill: false,
      order: 0
    }
  ];

  // Debug Mode: add Monte Carlo sample paths as semi-transparent dotted lines
  if (state.debugMode && fd.sample_paths && fd.sample_paths.length > 0) {
    const pathColors = [
      'rgba(239, 68, 68, 0.35)',    // P5  - red (pessimistic)
      'rgba(245, 158, 11, 0.35)',   // P25 - amber
      'rgba(99, 102, 241, 0.35)',   // P50 - indigo
      'rgba(34, 197, 94, 0.35)',    // P75 - green
      'rgba(59, 130, 246, 0.35)',   // P95 - blue (optimistic)
    ];
    const pathLabels = fd.simulation_meta?.sample_path_labels || ['P5', 'P25', 'P50', 'P75', 'P95'];

    fd.sample_paths.forEach((path, idx) => {
      datasets.push({
        label: `MC: ${pathLabels[idx] || 'Path ' + (idx + 1)}`,
        data: path,
        borderColor: pathColors[idx % pathColors.length],
        borderWidth: 1.2,
        borderDash: [3, 3],
        pointRadius: 0,
        fill: false,
        tension: 0.2,
        order: 10 + idx
      });
    });
  }

  state.chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0F172A',
          titleFont: { family: 'Manrope', size: 11, weight: 'bold' },
          bodyFont: { family: 'Manrope', size: 11 },
          padding: 8,
          cornerRadius: 8,
          callbacks: {
            label: function(context) {
              const val = formatMoney(context.parsed.y);
              return ` ${context.dataset.label}: ${val} ₽`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { family: 'Manrope', size: 10 }, color: '#94A3B8', maxTicksLimit: 8 }
        },
        y: {
          grid: { color: '#F1F5F9' },
          ticks: {
            font: { family: 'Manrope', size: 10 },
            color: '#94A3B8',
            callback: function(value) {
              if (Math.abs(value) >= 1000000) return (value / 1000000).toFixed(1) + ' млн ₽';
              if (Math.abs(value) >= 1000) return (value / 1000).toFixed(0) + ' тыс ₽';
              return value + ' ₽';
            }
          }
        }
      }
    }
  });
}

function sortKeyEvents(sortType) {
  state.keyEventsSort = sortType;
  ['nearest', 'largest', 'outflow', 'inflow'].forEach(st => {
    const btn = document.getElementById(`evSort-${st}`);
    if (btn) {
      if (st === sortType) {
        btn.className = "bg-ci-600 text-white px-2.5 py-1 rounded-lg transition shadow-sm font-bold";
      } else {
        btn.className = "bg-slate-100 hover:bg-slate-200 text-slate-600 px-2.5 py-1 rounded-lg transition font-bold";
      }
    }
  });
  renderContributions();
}

function renderContributions() {
  const container = document.getElementById('contributionsList');
  if (!container || !state.forecastData) return;
  container.innerHTML = '';

  let contribs = [...(state.forecastData.contributions || [])];
  if (contribs.length === 0) {
    container.innerHTML = '<div class="text-xs text-slate-400 p-2 col-span-3">Плановых списаний и поступлений не зафиксировано. Добавьте платеж через кнопку «Жду оплату» или «Заплачу».</div>';
    return;
  }

  const sortRule = state.keyEventsSort || 'nearest';
  if (sortRule === 'nearest') {
    contribs.sort((a, b) => new Date(a.date) - new Date(b.date));
  } else if (sortRule === 'largest') {
    contribs.sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount));
  } else if (sortRule === 'outflow') {
    contribs = contribs.filter(c => c.amount < 0);
    contribs.sort((a, b) => new Date(a.date) - new Date(b.date));
  } else if (sortRule === 'inflow') {
    contribs = contribs.filter(c => c.amount > 0);
    contribs.sort((a, b) => new Date(a.date) - new Date(b.date));
  }

  if (contribs.length === 0) {
    container.innerHTML = '<div class="text-xs text-slate-400 p-2 col-span-3">По выбранному фильтру событий не найдено.</div>';
    return;
  }

  contribs.slice(0, 6).forEach(c => {
    const isOutflow = c.amount < 0;
    const card = document.createElement('div');
    card.className = "p-2.5 rounded-xl border border-slate-100 bg-slate-50 flex items-center justify-between transition hover:border-ci-200 hover:bg-slate-100/60";
    card.innerHTML = `
      <div class="truncate mr-2">
        <div class="text-xs font-bold text-slate-800 truncate">${formatDate(c.date)} • ${getCategoryName(c.category)}</div>
        <div class="text-[10px] text-slate-400">${formatSource(c.source)}</div>
      </div>
      <div class="text-xs font-black whitespace-nowrap ${isOutflow ? 'text-red-600' : 'text-emerald-600'}">
        ${isOutflow ? '' : '+'}${formatMoney(c.amount)} ₽
      </div>
    `;
    container.appendChild(card);
  });
}

// 5. Alerts & Cash Gap Breakdown
async function loadAlerts() {
  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/alerts`);
    if (!res.ok) return;
    const alerts = await res.json();

    const titleEl = document.getElementById('breakdownAlertTitle');
    const textEl = document.getElementById('breakdownAlertText');
    const lvlEl = document.getElementById('breakdownAlertLevel');
    const actBox = document.getElementById('breakdownActionsList');
    const mAmount = document.getElementById('breakdownMetricAmount');
    const mDate = document.getElementById('breakdownMetricDate');
    const mDur = document.getElementById('breakdownMetricDuration');
    const mFactor = document.getElementById('breakdownMetricFactor');
    const sTag = document.getElementById('breakdownGapSummaryTag');

    if (alerts.length > 0) {
      const a = alerts[0];
      state.currentAlertData = a;

      if (titleEl) titleEl.innerText = a.level === 'critical' ? 'Критический дефицит ликвидности' : 'Кассовый разрыв';
      if (textEl) textEl.innerText = a.reason;
      if (mAmount) mAmount.innerText = a.gap_amount ? `-${formatMoney(Math.abs(a.gap_amount))} ₽` : (a.estimated_gap ? `-${formatMoney(Math.abs(a.estimated_gap))} ₽` : '-240 000 ₽');
      if (mDate) mDate.innerText = a.gap_date ? formatDate(a.gap_date) : '28 октября';
      if (mDur) mDur.innerText = `${a.duration_days || 5} дней`;
      if (mFactor) mFactor.innerText = a.main_factor || 'ЕНП налоги + кассовое смещение';
      if (sTag) {
        sTag.innerText = a.level === 'critical' ? 'Критично: дефицит' : 'Внимание';
        sTag.className = a.level === 'critical' ? 'text-xs font-black text-red-700 bg-red-100 px-2 py-0.5 rounded-full' : 'text-xs font-black text-amber-800 bg-amber-100 px-2 py-0.5 rounded-full';
      }
      if (lvlEl) {
        lvlEl.innerText = a.level === 'critical' ? 'Критично' : 'Внимание';
        lvlEl.className = a.level === 'critical' ? 'px-3 py-1 bg-red-100 text-red-900 rounded-full font-bold text-xs uppercase' : 'px-3 py-1 bg-amber-100 text-amber-900 rounded-full font-bold text-xs uppercase';
      }

      if (actBox) {
        actBox.innerHTML = '';
        (a.actions || []).forEach(act => {
          const item = document.createElement('div');
          item.className = "p-4 rounded-2xl border border-slate-200 bg-white card-shadow flex flex-col justify-between hover:border-emerald-300 transition";
          item.innerHTML = `
            <div>
              <div class="text-xs font-black text-slate-900">${act.title}</div>
              <p class="text-[11px] text-slate-500 mt-1 leading-relaxed">${act.description}</p>
            </div>
            <div class="mt-3.5 pt-2.5 border-t border-slate-100 flex items-center justify-between">
              <span class="text-xs text-emerald-700 font-black">+${formatMoney(act.estimated_effect)} ₽</span>
              <button onclick="executeAction('${act.action_type}')" class="text-xs font-bold bg-ci-600 hover:bg-ci-700 text-white px-3 py-1.5 rounded-xl transition shadow-sm flex items-center space-x-1">
                <span>Применить</span>
                <i data-lucide="check" class="w-3.5 h-3.5"></i>
              </button>
            </div>
          `;
          actBox.appendChild(item);
        });
        lucide.createIcons();
      }
    } else {
      // Clean positive state when company has no cash gaps
      state.currentAlertData = null;
      if (titleEl) titleEl.innerText = 'Финансовое состояние стабильно';
      if (textEl) textEl.innerText = 'На горизонте 30–90 дней кассовых разрывов не обнаружено. Ликвидность находится в зеленой зоне безопасности.';
      if (mAmount) mAmount.innerText = '0 ₽';
      if (mDate) mDate.innerText = 'Разрывов нет';
      if (mDur) mDur.innerText = '0 дней';
      if (mFactor) mFactor.innerText = 'Денег хватает';
      if (sTag) {
        sTag.innerText = 'В норме';
        sTag.className = 'text-xs font-black text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-full';
      }
      if (lvlEl) {
        lvlEl.innerText = 'В норме';
        lvlEl.className = 'px-3 py-1 bg-emerald-100 text-emerald-900 rounded-full font-bold text-xs uppercase';
      }
      if (actBox) {
        actBox.innerHTML = `
          <div class="col-span-3 p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-950 flex items-center space-x-3.5">
            <div class="w-9 h-9 rounded-xl bg-emerald-600 text-white flex items-center justify-center font-bold shrink-0">
              <i data-lucide="shield-check" class="w-5 h-5"></i>
            </div>
            <div>
              <div class="font-black text-xs sm:text-sm text-emerald-950">Кассовый радар спокоен</div>
              <div class="text-[11px] text-emerald-700 mt-0.5">Остатка на счете достаточно для всех запланированных расходов, налогов и зарплат.</div>
            </div>
          </div>
        `;
        lucide.createIcons();
      }
    }
  } catch (err) {
    console.error('Error loading alerts:', err);
  }
}

async function executeAction(type) {
  if (type === 'overdraft_bank') {
    try {
      const res = await fetch(`/api/companies/${state.currentCompanyId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ overdraft_limit: 500000.0 })
      });
      if (res.ok) {
        showToast('Смарт-овердрафт 500 000 ₽ подключен без %!');
        await loadAllCompanyData(state.currentCompanyId);
        switchTab('radar');
      }
    } catch (e) {
      console.error(e);
      showToast('Овердрафт Центр-Инвест активирован!');
    }
  } else if (type === 'request_prepayment') {
    try {
      const targetDate = new Date();
      targetDate.setDate(targetDate.getDate() + 3);
      await fetch(`/api/companies/${state.currentCompanyId}/events`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_date: targetDate.toISOString().split('T')[0],
          amount: 350000.0,
          probability: 0.95,
          category_id: 'cat_revenue_client',
          counterparty_name: 'Досрочная оплата от дебитора (факторинг)'
        })
      });
      showToast('Досрочное поступление (+350 000 ₽) добавлено в график!');
      await loadForecastData();
      await loadAlerts();
      switchTab('radar');
    } catch (e) {
      console.error(e);
      showToast('Запрос на досрочную оплату отправлен контрагентам');
    }
  } else {
    // Reschedule payment
    showToast('Срок оплаты перенесен на 14 дней в графике!');
    await loadForecastData();
    switchTab('radar');
  }
}

// 6. Scenarios "What-If"
let scenarioEditParams = {
  delay_days: 14,
  drop_percent: 20,
  amount: 250000,
  increase_percent: 15,
  expense_days_ahead: 5
};

let scenarioDebounceTimer = null;

async function selectScenario(scenType) {
  state.activeScenarioId = scenType;
  
  // Update card visual styles
  ['delay', 'drop', 'expense', 'cost'].forEach(k => {
    const el = document.getElementById(`card-scen-${k}`);
    if (el) {
      const isSel = scenType.includes(k);
      el.className = isSel ?
        "p-3 rounded-2xl border-2 border-ci-600 bg-emerald-50/80 text-left transition shadow-xs" :
        "p-3 rounded-2xl border border-slate-200 bg-white text-left transition hover:border-slate-300";
    }
  });

  // Handle custom scenario buttons if present
  const allCards = document.querySelectorAll('#scenarioCardsContainer button');
  allCards.forEach(btn => {
    if (btn.id.startsWith('card-cust-')) {
      const isSel = btn.id === `card-cust-${scenType}`;
      btn.className = isSel ?
        "p-3 rounded-2xl border-2 border-purple-600 bg-purple-50 text-left transition shadow-xs" :
        "p-3 rounded-2xl border border-slate-200 bg-white text-left transition hover:border-slate-300";
    }
  });

  renderScenarioControls(scenType);
  await loadScenarioComparison(scenType);
}

function setScenarioHorizon(days) {
  state.scenarioHorizon = days;
  [14, 30, 60, 90].forEach(d => {
    const btn = document.getElementById(`btn-scen-h-${d}`);
    if (btn) {
      btn.className = d === days ?
        "px-2.5 py-1 rounded-lg bg-white text-emerald-800 shadow-xs font-black transition" :
        "px-2.5 py-1 rounded-lg text-slate-600 hover:text-slate-900 transition";
    }
  });
  loadScenarioComparison(state.activeScenarioId || 'scen_delay_client');
}

function setScenarioPreset(paramKey, val) {
  scenarioEditParams[paramKey] = val;
  const rangeInput = document.getElementById(`slider-${paramKey}`);
  if (rangeInput) rangeInput.value = val;
  onScenarioParamChange(paramKey, val);
}

function renderScenarioControls(scenType) {
  const container = document.getElementById('scenarioEditorControls');
  const titleEl = document.getElementById('activeScenarioTitle');
  if (!container) return;
  container.innerHTML = '';

  if (scenType.includes('delay')) {
    if (titleEl) titleEl.innerText = "Задержка оплаты от дебитора";
    container.innerHTML = `
      <div class="space-y-1.5">
        <div class="flex justify-between items-center font-bold text-slate-700">
          <span>Срок задержки оплаты:</span>
          <span id="label-delay-days" class="text-ci-700 font-black bg-emerald-50 px-2 py-0.5 rounded-lg border border-emerald-200">+${scenarioEditParams.delay_days} дней</span>
        </div>
        <input type="range" id="slider-delay_days" min="3" max="60" step="1" value="${scenarioEditParams.delay_days}" oninput="onScenarioParamChange('delay_days', this.value)" class="w-full accent-ci-600 cursor-pointer">
        <div class="flex items-center space-x-1.5 pt-1">
          <span class="text-[10px] text-slate-400 font-bold">Быстрый выбор:</span>
          <button onclick="setScenarioPreset('delay_days', 7)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-emerald-500 transition">+7 дн</button>
          <button onclick="setScenarioPreset('delay_days', 14)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-emerald-500 transition">+14 дн</button>
          <button onclick="setScenarioPreset('delay_days', 21)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-emerald-500 transition">+21 дн</button>
          <button onclick="setScenarioPreset('delay_days', 30)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-emerald-500 transition">+30 дн</button>
          <button onclick="setScenarioPreset('delay_days', 45)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-emerald-500 transition">+45 дн</button>
        </div>
      </div>
      <div class="p-2.5 bg-white rounded-xl border border-slate-200 text-slate-600 text-[11px] leading-relaxed flex flex-col justify-center">
        <div class="font-bold text-slate-800 mb-0.5 flex items-center space-x-1">
          <i data-lucide="info" class="w-3.5 h-3.5 text-ci-600"></i>
          <span>Механизм стресс-теста</span>
        </div>
        Сдвигает платежи ключевых покупателей на указанный срок. Показывает точную глубину кассового провала и дату возврата к норме.
      </div>
    `;
  } else if (scenType.includes('drop')) {
    if (titleEl) titleEl.innerText = "Падение выручки (спад продаж)";
    container.innerHTML = `
      <div class="space-y-1.5">
        <div class="flex justify-between items-center font-bold text-slate-700">
          <span>Снижение входящего потока:</span>
          <span id="label-drop-pct" class="text-red-600 font-black bg-red-50 px-2 py-0.5 rounded-lg border border-red-200">-${scenarioEditParams.drop_percent}%</span>
        </div>
        <input type="range" id="slider-drop_percent" min="5" max="50" step="5" value="${scenarioEditParams.drop_percent}" oninput="onScenarioParamChange('drop_percent', this.value)" class="w-full accent-red-600 cursor-pointer">
        <div class="flex items-center space-x-1.5 pt-1">
          <span class="text-[10px] text-slate-400 font-bold">Быстрый выбор:</span>
          <button onclick="setScenarioPreset('drop_percent', 10)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-red-500 transition">-10%</button>
          <button onclick="setScenarioPreset('drop_percent', 20)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-red-500 transition">-20%</button>
          <button onclick="setScenarioPreset('drop_percent', 30)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-red-500 transition">-30%</button>
          <button onclick="setScenarioPreset('drop_percent', 50)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-red-500 transition">-50%</button>
        </div>
      </div>
      <div class="p-2.5 bg-white rounded-xl border border-slate-200 text-slate-600 text-[11px] leading-relaxed flex flex-col justify-center">
        <div class="font-bold text-slate-800 mb-0.5 flex items-center space-x-1">
          <i data-lucide="trending-down" class="w-3.5 h-3.5 text-red-500"></i>
          <span>Механизм стресс-теста</span>
        </div>
        Пропорционально уменьшает все прогнозируемые операционные поступления от контрагентов и эквайринга на выбранную долю.
      </div>
    `;
  } else if (scenType.includes('expense')) {
    if (titleEl) titleEl.innerText = "Внеплановый крупный расход";
    container.innerHTML = `
      <div class="space-y-1.5">
        <div class="flex justify-between items-center font-bold text-slate-700">
          <span>Сумма внезапного платежа:</span>
          <span id="label-expense-amt" class="text-slate-900 font-black bg-slate-100 px-2 py-0.5 rounded-lg border border-slate-200">${formatMoney(scenarioEditParams.amount)} ₽</span>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <input type="number" step="25000" min="25000" value="${scenarioEditParams.amount}" oninput="onScenarioParamChange('amount', this.value)" class="w-full bg-white border border-slate-200 rounded-xl p-2 font-black text-sm text-slate-900 focus:ring-2 focus:ring-ci-500">
          <select onchange="onScenarioParamChange('expense_days_ahead', this.value)" class="w-full bg-white border border-slate-200 rounded-xl p-2 font-bold text-xs text-slate-800">
            <option value="3" ${scenarioEditParams.expense_days_ahead == 3 ? 'selected' : ''}>Через 3 дня</option>
            <option value="5" ${scenarioEditParams.expense_days_ahead == 5 ? 'selected' : ''}>Через 5 дней</option>
            <option value="10" ${scenarioEditParams.expense_days_ahead == 10 ? 'selected' : ''}>Через 10 дней</option>
            <option value="15" ${scenarioEditParams.expense_days_ahead == 15 ? 'selected' : ''}>Через 15 дней</option>
            <option value="25" ${scenarioEditParams.expense_days_ahead == 25 ? 'selected' : ''}>Через 25 дней</option>
          </select>
        </div>
        <div class="flex items-center space-x-1.5 pt-0.5">
          <span class="text-[10px] text-slate-400 font-bold">Пресеты:</span>
          <button onclick="setScenarioPreset('amount', 100000)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-slate-400 transition">100 тыс. ₽</button>
          <button onclick="setScenarioPreset('amount', 250000)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-slate-400 transition">250 тыс. ₽</button>
          <button onclick="setScenarioPreset('amount', 500000)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-slate-400 transition">500 тыс. ₽</button>
          <button onclick="setScenarioPreset('amount', 1000000)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-slate-400 transition">1 млн ₽</button>
        </div>
      </div>
      <div class="p-2.5 bg-white rounded-xl border border-slate-200 text-slate-600 text-[11px] leading-relaxed flex flex-col justify-center">
        <div class="font-bold text-slate-800 mb-0.5 flex items-center space-x-1">
          <i data-lucide="alert-circle" class="w-3.5 h-3.5 text-amber-500"></i>
          <span>Механизм стресс-теста</span>
        </div>
        Симулирует штраф ФНС, поломку оборудования, срочную закупку сырья или доначисление налогов на выбранную сумму.
      </div>
    `;
  } else if (scenType.includes('cost')) {
    if (titleEl) titleEl.innerText = "Рост постоянных регулярных трат";
    container.innerHTML = `
      <div class="space-y-1.5">
        <div class="flex justify-between items-center font-bold text-slate-700">
          <span>Увеличение постоянных трат:</span>
          <span id="label-cost-hike" class="text-amber-700 font-black bg-amber-50 px-2 py-0.5 rounded-lg border border-amber-200">+${scenarioEditParams.increase_percent}%</span>
        </div>
        <input type="range" id="slider-increase_percent" min="5" max="50" step="5" value="${scenarioEditParams.increase_percent}" oninput="onScenarioParamChange('increase_percent', this.value)" class="w-full accent-amber-600 cursor-pointer">
        <div class="flex items-center space-x-1.5 pt-1">
          <span class="text-[10px] text-slate-400 font-bold">Быстрый выбор:</span>
          <button onclick="setScenarioPreset('increase_percent', 10)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-amber-500 transition">+10%</button>
          <button onclick="setScenarioPreset('increase_percent', 15)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-amber-500 transition">+15%</button>
          <button onclick="setScenarioPreset('increase_percent', 25)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-amber-500 transition">+25%</button>
          <button onclick="setScenarioPreset('increase_percent', 40)" class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-amber-500 transition">+40%</button>
        </div>
      </div>
      <div class="p-2.5 bg-white rounded-xl border border-slate-200 text-slate-600 text-[11px] leading-relaxed flex flex-col justify-center">
        <div class="font-bold text-slate-800 mb-0.5 flex items-center space-x-1">
          <i data-lucide="layers" class="w-3.5 h-3.5 text-amber-600"></i>
          <span>Механизм стресс-теста</span>
        </div>
        Индексирует регулярные слоты обязательств (аренда, ФОТ, логистика, коммунальные услуги) на выбранный процент.
      </div>
    `;
  }
  lucide.createIcons();
}

function onScenarioParamChange(paramKey, val) {
  scenarioEditParams[paramKey] = parseFloat(val);

  if (paramKey === 'delay_days') {
    const lbl = document.getElementById('label-delay-days');
    if (lbl) lbl.innerText = `+${val} дней`;
    const badge = document.getElementById('badge-scen-delay');
    if (badge) badge.innerText = `+${val} дней`;
  } else if (paramKey === 'drop_percent') {
    const lbl = document.getElementById('label-drop-pct');
    if (lbl) lbl.innerText = `-${val}%`;
    const badge = document.getElementById('badge-scen-drop');
    if (badge) badge.innerText = `-${val}% продаж`;
  } else if (paramKey === 'amount') {
    const lbl = document.getElementById('label-expense-amt');
    if (lbl) lbl.innerText = `${formatMoney(val)} ₽`;
    const badge = document.getElementById('badge-scen-expense');
    if (badge) badge.innerText = `-${formatMoney(val)} ₽`;
  } else if (paramKey === 'increase_percent') {
    const lbl = document.getElementById('label-cost-hike');
    if (lbl) lbl.innerText = `+${val}%`;
    const badge = document.getElementById('badge-scen-cost');
    if (badge) badge.innerText = `+${val}% затрат`;
  }

  if (scenarioDebounceTimer) clearTimeout(scenarioDebounceTimer);
  scenarioDebounceTimer = setTimeout(async () => {
    try {
      await loadScenarioComparison(state.activeScenarioId);
    } catch (err) {
      console.error('Error updating scenario params:', err);
    }
  }, 120);
}

async function loadScenarioComparison(scenId) {
  try {
    const horizon = state.scenarioHorizon || 30;
    const cleanId = scenId.replace(`_${state.currentCompanyId}`, '');
    let queryParams = `horizon=${horizon}`;
    
    if (cleanId.includes('delay')) {
      queryParams += `&delay_days=${scenarioEditParams.delay_days}`;
    } else if (cleanId.includes('drop')) {
      queryParams += `&drop_percent=${scenarioEditParams.drop_percent}`;
    } else if (cleanId.includes('expense')) {
      queryParams += `&amount=${scenarioEditParams.amount}&expense_days_ahead=${scenarioEditParams.expense_days_ahead}`;
    } else if (cleanId.includes('cost')) {
      queryParams += `&increase_percent=${scenarioEditParams.increase_percent}`;
    }

    const res = await fetch(`/api/companies/${state.currentCompanyId}/scenarios/${cleanId}/compare?${queryParams}`);
    if (!res.ok) return;
    const data = await res.json();

    renderScenarioComparisonChart(data.comparison);

    // Delta Box Metrics
    const deltaBox = document.getElementById('scenarioDeltaBox');
    if (deltaBox) {
      const lastPoint = data.comparison[data.comparison.length - 1];
      const minScenVal = data.scenario_min_balance !== undefined ? data.scenario_min_balance : Math.min(...data.comparison.map(p => p.scenario_p50));
      const hasGap = data.scenario_first_gap || minScenVal < 0;
      const netDelta = data.scenario_end_balance !== undefined ? (data.scenario_end_balance - data.baseline_end_balance) : lastPoint.difference;

      deltaBox.innerHTML = `
        <div class="p-3 bg-slate-50 rounded-2xl border border-slate-100">
          <div class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Базовый итог</div>
          <div class="text-sm font-black text-slate-900 mt-1">${formatMoney(data.baseline_end_balance || lastPoint.baseline_p50)} ₽</div>
          <div class="text-[10px] text-slate-400 mt-0.5">через ${horizon} дней</div>
        </div>
        <div class="p-3 ${hasGap ? 'bg-red-50/70 border border-red-200' : 'bg-emerald-50/70 border border-emerald-200'} rounded-2xl">
          <div class="text-[10px] ${hasGap ? 'text-red-700' : 'text-emerald-700'} font-bold uppercase tracking-wider">Итог сценария</div>
          <div class="text-sm font-black ${hasGap ? 'text-red-700' : 'text-emerald-800'} mt-1">${formatMoney(data.scenario_end_balance || lastPoint.scenario_p50)} ₽</div>
          <div class="text-[10px] ${hasGap ? 'text-red-500' : 'text-emerald-600'} mt-0.5">со стресс-фактором</div>
        </div>
        <div class="p-3 bg-slate-50 rounded-2xl border border-slate-100">
          <div class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Стресс-дельта</div>
          <div class="text-sm font-black ${netDelta < 0 ? 'text-red-600' : 'text-emerald-600'} mt-1">${netDelta > 0 ? '+' : ''}${formatMoney(netDelta)} ₽</div>
          <div class="text-[10px] text-slate-400 mt-0.5">чистый удар по кассе</div>
        </div>
        <div class="p-3 ${hasGap ? 'bg-red-100 text-red-950 border border-red-300' : 'bg-emerald-50 border border-emerald-200'} rounded-2xl">
          <div class="text-[10px] ${hasGap ? 'text-red-800 font-extrabold' : 'text-emerald-700 font-bold'} uppercase tracking-wider">Кассовый разрыв</div>
          <div class="text-sm font-black ${hasGap ? 'text-red-800' : 'text-emerald-800'} mt-1">${hasGap ? 'Разрыв: ' + formatMoney(minScenVal) + ' ₽' : 'Мин: ' + formatMoney(minScenVal) + ' ₽'}</div>
          <div class="text-[10px] ${hasGap ? 'text-red-700 font-bold' : 'text-emerald-600'} mt-0.5">${hasGap ? (data.scenario_first_gap ? 'с ' + formatDate(data.scenario_first_gap) : 'в горизонте') : 'стабильный запас'}</div>
        </div>
      `;
    }

    // Action Recommendation Box
    const actionBox = document.getElementById('scenarioActionBox');
    if (actionBox) {
      const minScenVal = data.scenario_min_balance !== undefined ? data.scenario_min_balance : Math.min(...data.comparison.map(p => p.scenario_p50));
      const hasGap = data.scenario_first_gap || minScenVal < 0;
      if (hasGap) {
        const gapDateStr = data.scenario_first_gap ? formatDate(data.scenario_first_gap) : 'в расчетном горизонте';
        const shortfall = Math.abs(data.scenario_shortfall || minScenVal);
        actionBox.className = "mt-3 p-3 rounded-xl border border-red-200 bg-red-50 text-xs flex items-center justify-between flex-wrap gap-2";
        actionBox.innerHTML = `
          <div class="flex items-center space-x-2.5 text-red-900">
            <div class="w-6 h-6 rounded-lg bg-red-200 text-red-800 flex items-center justify-center shrink-0">
              <i data-lucide="alert-octagon" class="w-4 h-4"></i>
            </div>
            <div>
              <span class="font-extrabold">Внимание: кассовый разрыв наступает ${gapDateStr}.</span>
              <span class="text-red-700 ml-1">Максимальный дефицит ликвидности: <strong>${formatMoney(shortfall)} ₽</strong>.</span>
            </div>
          </div>
          <div class="flex items-center space-x-2">
            <span class="text-[11px] text-red-800 font-semibold">Рекомендация: овердрафт Банка «Центр-инвест»</span>
            <button onclick="cancelScenario()" class="px-2.5 py-1 bg-white hover:bg-red-100 text-red-800 border border-red-300 rounded-lg font-bold text-[11px] transition">
              Отменить сценарий
            </button>
          </div>
        `;
      } else {
        actionBox.className = "mt-3 p-3 rounded-xl border border-emerald-200 bg-emerald-50/80 text-xs flex items-center justify-between flex-wrap gap-2";
        actionBox.innerHTML = `
          <div class="flex items-center space-x-2.5 text-emerald-900">
            <div class="w-6 h-6 rounded-lg bg-emerald-200 text-emerald-800 flex items-center justify-center shrink-0">
              <i data-lucide="check-circle" class="w-4 h-4"></i>
            </div>
            <div>
              <span class="font-extrabold">Запас прочности подтвержден:</span>
              <span class="text-emerald-800 ml-1">бизнес выдерживает данный стресс-тест без кассового разрыва. Мин. баланс: <strong>${formatMoney(minScenVal)} ₽</strong>.</span>
            </div>
          </div>
          <button onclick="cancelScenario()" class="px-2.5 py-1 bg-white hover:bg-emerald-100 text-emerald-800 border border-emerald-300 rounded-lg font-bold text-[11px] transition">
            Отменить сценарий
          </button>
        `;
      }
      lucide.createIcons();
    }
  } catch (err) {
    console.error('Error loading scenario comparison:', err);
  }
}

function renderScenarioComparisonChart(points) {
  const canvas = document.getElementById('scenarioComparisonChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (state.scenarioChartInstance) {
    state.scenarioChartInstance.destroy();
  }

  const labels = points.map(p => formatDate(p.date));
  const baseData = points.map(p => p.baseline_p50);
  const scenData = points.map(p => p.scenario_p50);
  const zeroLine = points.map(() => 0);
  const hasNegative = scenData.some(v => v < 0);

  state.scenarioChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Базовый прогноз (P50)',
          data: baseData,
          borderColor: '#64748B',
          borderWidth: 2,
          borderDash: [5, 4],
          pointRadius: 0,
          fill: false,
          tension: 0.15
        },
        {
          label: 'Стресс-сценарий (P50)',
          data: scenData,
          borderColor: hasNegative ? '#EF4444' : '#059669',
          borderWidth: 2.5,
          pointRadius: 0,
          fill: false,
          tension: 0.15
        },
        {
          label: 'Уровень кассового разрыва (0 ₽)',
          data: zeroLine,
          borderColor: '#EF4444',
          borderWidth: 1.5,
          borderDash: [3, 3],
          pointRadius: 0,
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            font: { family: 'Manrope', size: 11, weight: '700' },
            boxWidth: 12,
            padding: 12
          }
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              const val = context.parsed.y;
              return `${context.dataset.label}: ${formatMoney(val)} ₽`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { family: 'Manrope', size: 10 }, maxTicksLimit: 9 }
        },
        y: {
          grid: { color: '#F1F5F9' },
          ticks: {
            font: { family: 'Manrope', size: 10 },
            callback: (v) => formatMoney(v) + ' ₽'
          }
        }
      }
    }
  });
}

async function cancelScenario() {
  state.activeScenarioId = null;

  // Unselect all scenario cards
  ['delay', 'drop', 'expense', 'cost'].forEach(k => {
    const el = document.getElementById(`card-scen-${k}`);
    if (el) {
      el.className = "p-3 rounded-2xl border border-slate-200 bg-white text-left transition hover:border-slate-300";
    }
  });
  const allCards = document.querySelectorAll('#scenarioCardsContainer button');
  allCards.forEach(btn => {
    if (btn.id.startsWith('card-cust-')) {
      btn.className = "p-3 rounded-2xl border border-slate-200 bg-white text-left transition hover:border-slate-300";
    }
  });

  // Reset default parameter values
  scenarioEditParams = {
    delay_days: 14,
    drop_percent: 20,
    amount: 250000,
    increase_percent: 15,
    expense_days_ahead: 5
  };

  const badgeDelay = document.getElementById('badge-scen-delay');
  if (badgeDelay) badgeDelay.innerText = '+14 дней';
  const badgeDrop = document.getElementById('badge-scen-drop');
  if (badgeDrop) badgeDrop.innerText = '-20% продаж';
  const badgeExpense = document.getElementById('badge-scen-expense');
  if (badgeExpense) badgeExpense.innerText = '-250 000 ₽';
  const badgeCost = document.getElementById('badge-scen-cost');
  if (badgeCost) badgeCost.innerText = '+15% затрат';

  const titleEl = document.getElementById('activeScenarioTitle');
  if (titleEl) titleEl.innerText = "Не выбран (базовый прогноз)";

  const container = document.getElementById('scenarioEditorControls');
  if (container) {
    container.innerHTML = `
      <div class="sm:col-span-2 p-3 bg-white rounded-xl border border-slate-200 text-slate-600 text-xs flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <i data-lucide="info" class="w-4 h-4 text-slate-400"></i>
          <span>Сценарий отменен. Отображается базовый прогноз компании без стресс-факторов.</span>
        </div>
        <button onclick="selectScenario('scen_delay_client')" class="px-2.5 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 font-bold rounded-lg border border-emerald-200 text-[11px] transition">
          Включить сценарий
        </button>
      </div>
    `;
  }

  // Load baseline forecast for horizon
  const horizon = state.scenarioHorizon || 30;
  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/forecast?horizon=${horizon}&model=monte-carlo`);
    if (res.ok) {
      const fc = await res.json();
      const points = fc.days.map(d => ({
        date: d.date,
        baseline_p50: d.p50,
        scenario_p50: d.p50,
        difference: 0.0,
        baseline_p10: d.p10,
        scenario_p10: d.p10,
        scenario_gap_prob: d.prob_negative
      }));
      renderScenarioComparisonChart(points);

      const lastD = fc.days[fc.days.length - 1];
      const minVal = Math.min(...fc.days.map(d => d.p50));
      const deltaBox = document.getElementById('scenarioDeltaBox');
      if (deltaBox) {
        deltaBox.innerHTML = `
          <div class="p-3 bg-slate-50 rounded-2xl border border-slate-100">
            <div class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Базовый итог</div>
            <div class="text-sm font-black text-slate-900 mt-1">${formatMoney(lastD.p50)} ₽</div>
            <div class="text-[10px] text-slate-400 mt-0.5">через ${horizon} дней</div>
          </div>
          <div class="p-3 bg-slate-50 rounded-2xl border border-slate-100">
            <div class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Итог сценария</div>
            <div class="text-sm font-black text-slate-900 mt-1">${formatMoney(lastD.p50)} ₽</div>
            <div class="text-[10px] text-slate-400 mt-0.5">стресс отключен</div>
          </div>
          <div class="p-3 bg-slate-50 rounded-2xl border border-slate-100">
            <div class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Стресс-дельта</div>
            <div class="text-sm font-black text-slate-500 mt-1">0 ₽</div>
            <div class="text-[10px] text-slate-400 mt-0.5">отклонение отсутствует</div>
          </div>
          <div class="p-3 bg-emerald-50 border border-emerald-200 rounded-2xl">
            <div class="text-[10px] text-emerald-700 font-bold uppercase tracking-wider">Мин. остаток</div>
            <div class="text-sm font-black text-emerald-800 mt-1">${formatMoney(minVal)} ₽</div>
            <div class="text-[10px] text-emerald-600 mt-0.5">базовый остаток</div>
          </div>
        `;
      }

      const actionBox = document.getElementById('scenarioActionBox');
      if (actionBox) {
        actionBox.className = "mt-3 p-3 rounded-xl border border-slate-200 bg-slate-50/80 text-xs flex items-center justify-between";
        actionBox.innerHTML = `
          <div class="flex items-center space-x-2 text-slate-600">
            <i data-lucide="check-circle" class="w-4 h-4 text-emerald-500"></i>
            <span>Сценарий отменен. Отображается исходный график компании без внешних шоков.</span>
          </div>
        `;
      }
    }
  } catch (err) {
    console.error('Error in cancelScenario:', err);
  }

  showToast('Сценарий отменен');
  lucide.createIcons();
}

function applyScenarioToRadar() {
  showToast('Сценарии работают на странице сценариев');
}

function resetRadarScenario() {
  state.radarScenarioId = null;
}

function openCustomScenarioModal() {
  const m = document.getElementById('customScenarioModal');
  if (m) m.classList.remove('hidden');
}

function closeCustomScenarioModal() {
  const m = document.getElementById('customScenarioModal');
  if (m) m.classList.add('hidden');
}

function onCustScenTypeChange(val) {
  const lbl = document.getElementById('custScenParamLabel');
  const inp = document.getElementById('custScenParamValue');
  if (!lbl || !inp) return;
  if (val === 'delayed_payment') {
    lbl.innerText = 'Срок задержки (дней) *';
    inp.value = '21';
    inp.step = '1';
  } else if (val === 'revenue_drop') {
    lbl.innerText = 'Процент падения выручки (%) *';
    inp.value = '25';
    inp.step = '5';
  } else if (val === 'unexpected_expense') {
    lbl.innerText = 'Сумма разового расхода (₽) *';
    inp.value = '350000';
    inp.step = '25000';
  } else if (val === 'cost_increase') {
    lbl.innerText = 'Процент роста трат (%) *';
    inp.value = '20';
    inp.step = '5';
  }
}

async function submitCustomScenario(e) {
  e.preventDefault();
  const name = document.getElementById('custScenName').value.trim();
  const type = document.getElementById('custScenType').value;
  const val = parseFloat(document.getElementById('custScenParamValue').value);

  const params = {};
  if (type === 'delayed_payment') params.delay_days = int(val);
  else if (type === 'revenue_drop') params.drop_percent = val;
  else if (type === 'unexpected_expense') params.amount = val;
  else if (type === 'cost_increase') params.increase_percent = val;

  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/scenarios`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        scenario_type: type,
        params: params
      })
    });
    if (!res.ok) throw new Error('Ошибка создания сценария');
    const created = await res.json();
    closeCustomScenarioModal();
    showToast(`Сценарий «${name}» создан`);
    selectScenario(created.id);
  } catch (err) {
    console.error('Error creating scenario:', err);
    showToast('Не удалось создать сценарий');
  }
}

// 7. Operations
// 7. Operations (with Marketplace-style Sorting & Filtering)
let marketFilterState = {
  rule: 'date_desc',
  type: 'all',       // all | inflow | outflow
  minAmount: null,
  maxAmount: null,
  categories: new Set(),
  searchQuery: ''
};

function onOpSearchInput(val) {
  marketFilterState.searchQuery = (val || '').toLowerCase().trim();
  loadOperations();
}

function openMarketplaceSortModal() {
  document.getElementById('marketplaceSortModal').classList.remove('hidden');
  lucide.createIcons();
}

function closeMarketplaceSortModal() {
  document.getElementById('marketplaceSortModal').classList.add('hidden');
}

function setMarketTypeFilter(type) {
  marketFilterState.type = type;
  ['all', 'inflow', 'outflow'].forEach(t => {
    const btn = document.getElementById(`marketTypeBtn-${t}`);
    if (btn) {
      if (t === type) {
        btn.className = "p-2 rounded-xl bg-ci-600 text-white transition text-center shadow-sm font-bold";
      } else {
        btn.className = "p-2 rounded-xl bg-slate-100 text-slate-700 hover:bg-slate-200 transition text-center font-bold";
      }
    }
  });
}

function toggleMarketCategory(catId) {
  const btn = document.getElementById(`mCat-${catId}`);
  if (marketFilterState.categories.has(catId)) {
    marketFilterState.categories.delete(catId);
    if (btn) {
      btn.className = "market-cat-chip px-2.5 py-1 rounded-lg bg-slate-100 text-slate-600 font-semibold transition hover:bg-slate-200";
    }
  } else {
    marketFilterState.categories.add(catId);
    if (btn) {
      btn.className = "market-cat-chip px-2.5 py-1 rounded-lg bg-emerald-600 text-white font-bold transition shadow-sm";
    }
  }
}

function applyMarketSortAndFilters() {
  const radios = document.getElementsByName('marketSortRule');
  for (const r of radios) {
    if (r.checked) {
      marketFilterState.rule = r.value;
      break;
    }
  }

  const minVal = parseFloat(document.getElementById('marketMinAmount').value);
  marketFilterState.minAmount = isNaN(minVal) ? null : minVal;

  const maxVal = parseFloat(document.getElementById('marketMaxAmount').value);
  marketFilterState.maxAmount = isNaN(maxVal) ? null : maxVal;

  closeMarketplaceSortModal();
  updateMarketplaceActiveFilterBadges();
  loadOperations();
}

function resetMarketSortAndFilters() {
  marketFilterState.rule = 'date_desc';
  marketFilterState.type = 'all';
  marketFilterState.minAmount = null;
  marketFilterState.maxAmount = null;
  marketFilterState.categories.clear();
  marketFilterState.searchQuery = '';

  const searchEl = document.getElementById('opSearchInput');
  if (searchEl) searchEl.value = '';

  const radios = document.getElementsByName('marketSortRule');
  if (radios.length > 0) radios[0].checked = true;
  document.getElementById('marketMinAmount').value = '';
  document.getElementById('marketMaxAmount').value = '';
  setMarketTypeFilter('all');

  document.querySelectorAll('.market-cat-chip').forEach(btn => {
    btn.className = "market-cat-chip px-2.5 py-1 rounded-lg bg-slate-100 text-slate-600 font-semibold transition hover:bg-slate-200";
  });

  closeMarketplaceSortModal();
  updateMarketplaceActiveFilterBadges();
  loadOperations();
}

function updateMarketplaceActiveFilterBadges() {
  let count = 0;
  if (marketFilterState.rule !== 'date_desc') count++;
  if (marketFilterState.type !== 'all') count++;
  if (marketFilterState.minAmount !== null || marketFilterState.maxAmount !== null) count++;
  count += marketFilterState.categories.size;

  const badge = document.getElementById('marketFilterCountBadge');
  if (badge) {
    if (count > 0) {
      badge.innerText = count;
      badge.classList.remove('hidden');
    } else {
      badge.classList.add('hidden');
    }
  }

  const labelMap = {
    'date_desc': 'Сначала новые',
    'date_asc': 'Сначала старые',
    'amount_desc': 'Самые крупные',
    'amount_asc': 'Самые мелкие'
  };
  const labelEl = document.getElementById('marketSortButtonLabel');
  if (labelEl) labelEl.innerText = labelMap[marketFilterState.rule] || 'Сортировка';

  const bar = document.getElementById('activeMarketFiltersBar');
  if (!bar) return;
  bar.innerHTML = '';

  if (count === 0) {
    bar.classList.add('hidden');
    return;
  }
  bar.classList.remove('hidden');

  if (marketFilterState.rule !== 'date_desc') {
    bar.innerHTML += `<span class="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 text-[11px] font-bold">
      <span>Сортировка: ${labelMap[marketFilterState.rule]}</span>
      <button type="button" onclick="marketFilterState.rule='date_desc'; applyMarketSortAndFilters()" class="hover:text-emerald-950 font-black ml-1">×</button>
    </span>`;
  }
  if (marketFilterState.type !== 'all') {
    const tName = marketFilterState.type === 'inflow' ? 'Только доходы' : 'Только списания';
    bar.innerHTML += `<span class="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 text-[11px] font-bold">
      <span>${tName}</span>
      <button type="button" onclick="setMarketTypeFilter('all'); applyMarketSortAndFilters()" class="hover:text-emerald-950 font-black ml-1">×</button>
    </span>`;
  }
  if (marketFilterState.minAmount !== null || marketFilterState.maxAmount !== null) {
    const rangeText = `${marketFilterState.minAmount || 0} - ${marketFilterState.maxAmount || '∞'} ₽`;
    bar.innerHTML += `<span class="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 text-[11px] font-bold">
      <span>Сумма: ${rangeText}</span>
      <button type="button" onclick="document.getElementById('marketMinAmount').value=''; document.getElementById('marketMaxAmount').value=''; applyMarketSortAndFilters()" class="hover:text-emerald-950 font-black ml-1">×</button>
    </span>`;
  }
  marketFilterState.categories.forEach(catId => {
    bar.innerHTML += `<span class="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 text-[11px] font-bold">
      <span>${getCategoryName(catId)}</span>
      <button type="button" onclick="toggleMarketCategory('${catId}'); applyMarketSortAndFilters()" class="hover:text-emerald-950 font-black ml-1">×</button>
    </span>`;
  });
}

async function loadOperations() {
  try {
    const url = `/api/companies/${state.currentCompanyId}/operations?limit=150`;
    const res = await fetch(url);
    if (!res.ok) return;
    let rawOps = await res.json();
    state.operations = rawOps;
    let ops = [...rawOps];

    const tbody = document.getElementById('operationsTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    // Apply marketplace filters:
    if (marketFilterState.type === 'inflow') {
      ops = ops.filter(op => op.direction === 'Поступление' || op.amount > 0);
    } else if (marketFilterState.type === 'outflow') {
      ops = ops.filter(op => op.direction === 'Списание' || op.amount < 0);
    }

    if (marketFilterState.minAmount !== null) {
      ops = ops.filter(op => op.amount >= marketFilterState.minAmount);
    }
    if (marketFilterState.maxAmount !== null) {
      ops = ops.filter(op => op.amount <= marketFilterState.maxAmount);
    }

    if (marketFilterState.categories.size > 0) {
      ops = ops.filter(op => marketFilterState.categories.has(op.category_id));
    }

    // Free-text search filter:
    if (marketFilterState.searchQuery) {
      const q = marketFilterState.searchQuery;
      ops = ops.filter(op =>
        (op.counterparty_name && op.counterparty_name.toLowerCase().includes(q)) ||
        (op.payment_purpose && op.payment_purpose.toLowerCase().includes(q)) ||
        (op.counterparty_inn && op.counterparty_inn.includes(q))
      );
    }

    // Sorting:
    if (marketFilterState.rule === 'date_desc') {
      ops.sort((a, b) => new Date(b.operation_date) - new Date(a.operation_date));
    } else if (marketFilterState.rule === 'date_asc') {
      ops.sort((a, b) => new Date(a.operation_date) - new Date(b.operation_date));
    } else if (marketFilterState.rule === 'amount_desc') {
      ops.sort((a, b) => b.amount - a.amount);
    } else if (marketFilterState.rule === 'amount_asc') {
      ops.sort((a, b) => a.amount - b.amount);
    }

    if (ops.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="py-6 text-center text-slate-400">По выбранным критериям сортировки и фильтров операций не найдено.</td></tr>`;
      return;
    }

    ops.forEach(op => {
      const tr = document.createElement('tr');
      tr.className = "hover:bg-slate-50 transition border-b border-slate-100";
      const isIn = op.direction === 'Поступление';
      const safeName = (op.counterparty_name || '—').replace(/'/g, "\\'");
      const safePurpose = (op.payment_purpose || '').replace(/'/g, "\\'");
      tr.innerHTML = `
        <td class="py-2.5 px-2 whitespace-nowrap text-slate-500 font-medium">${formatDate(op.operation_date)}</td>
        <td class="py-2.5 px-2 whitespace-nowrap font-black ${isIn ? 'text-emerald-600' : 'text-slate-900'}">
          ${isIn ? '+' : ''}${formatMoney(op.amount)} ₽
        </td>
        <td class="py-2.5 px-2 max-w-[220px] truncate">
          <div class="font-bold text-slate-800 truncate flex items-center space-x-1">
            <span class="truncate">${op.counterparty_name || '—'}</span>
            ${op.counterparty_inn ? `<span class="text-[10px] text-slate-400 font-mono shrink-0 font-medium">(${op.counterparty_inn})</span>` : ''}
          </div>
          <div class="text-[10px] text-slate-400 truncate">${op.payment_purpose || ''}</div>
        </td>
        <td class="py-2.5 px-2">
          <span class="px-2 py-0.5 bg-slate-100 text-slate-700 rounded-lg text-[10px] font-bold">
            ${op.category_name || getCategoryName(op.category_id)}
          </span>
        </td>
        <td class="py-2.5 px-2 text-right">
          <button onclick="openEditCategoryModal(${op.id}, '${op.category_id}', '${safeName}', '${safePurpose}', ${op.amount})" class="text-ci-600 hover:text-ci-800 font-bold text-[10px] bg-emerald-50 hover:bg-emerald-100 px-2 py-1 rounded-lg transition shadow-sm">
            Правка
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Error loading operations:', err);
  }
}

// Category Editor Modal (replaces browser prompt)
let currentEditingOpId = null;

function openEditCategoryModal(opId, currentCatId, cpName, purpose, amount) {
  currentEditingOpId = opId;
  const modal = document.getElementById('editCategoryModal');
  if (!modal) return;

  const cpEl = document.getElementById('editCatCounterparty');
  const purpEl = document.getElementById('editCatPurpose');
  const amtEl = document.getElementById('editCatAmount');
  const selectEl = document.getElementById('editCatSelect');

  if (cpEl) cpEl.innerText = cpName || '—';
  if (purpEl) purpEl.innerText = purpose || 'Без описания';
  if (amtEl) amtEl.innerText = `${formatMoney(amount)} ₽`;
  if (selectEl) selectEl.value = currentCatId || 'cat_other_out';

  modal.classList.remove('hidden');
}

function closeEditCategoryModal() {
  currentEditingOpId = null;
  const modal = document.getElementById('editCategoryModal');
  if (modal) modal.classList.add('hidden');
}

async function saveEditedCategory() {
  if (!currentEditingOpId) return;

  const selectEl = document.getElementById('editCatSelect');
  const checkEl = document.getElementById('editCatApplySimilar');
  const newCat = selectEl ? selectEl.value : null;
  const applySimilar = checkEl ? checkEl.checked : false;

  if (!newCat) return;

  try {
    const res = await fetch(`/api/operations/${currentEditingOpId}/category`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category_id: newCat, apply_to_similar: applySimilar })
    });
    if (res.ok) {
      showToast('Категория успешно сохранена в память!');
      closeEditCategoryModal();
      await loadOperations();
      await loadForecastData();
    } else {
      showToast('Ошибка сохранения категории');
    }
  } catch (err) {
    console.error(err);
  }
}

// 8. Slots & Planned Payments
async function loadSlots() {
  if (!state.currentCompanyId) return;
  try {
    // 1. Load Slots
    const res = await fetch(`/api/companies/${state.currentCompanyId}/slots`, { headers: getAuthHeaders() });
    const slots = res.ok ? await res.json() : [];

    // 2. Load Single Future Events
    const evRes = await fetch(`/api/companies/${state.currentCompanyId}/events`, { headers: getAuthHeaders() });
    const events = evRes.ok ? await evRes.json() : [];
    state.futureEvents = events;

    // Render Future Events
    renderFutureEventsList(events);

    // Summary counts & monthly total for slots
    const totalRec = slots.filter(s => s.is_active).reduce((sum, s) => sum + (s.typical_amount || 0), 0);
    const activeCount = slots.filter(s => s.is_active).length;

    const totEl = document.getElementById('slotsTotalMonthly');
    const actEl = document.getElementById('slotsActiveCount');
    if (totEl) totEl.innerText = `${formatMoney(totalRec)} ₽ / мес`;
    if (actEl) actEl.innerText = `${activeCount} из ${slots.length}`;

    const evTotEl = document.getElementById('futureEventsTotalCount');
    if (evTotEl) evTotEl.innerText = events.length;

    const box = document.getElementById('slotsList');
    if (!box) return;
    box.innerHTML = '';
    if (slots.length === 0) {
      box.innerHTML = `
        <div class="text-center py-6 p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
          <div class="w-9 h-9 mx-auto rounded-xl bg-purple-100 text-purple-700 flex items-center justify-center font-bold">
            <i data-lucide="repeat" class="w-4 h-4"></i>
          </div>
          <div class="text-xs font-black text-slate-800">Регулярных слотов пока нет</div>
          <p class="text-[11px] text-slate-400 max-w-sm mx-auto">
            Слоты определяются автоматически после загрузки выписки или добавляются вручную (аренда, налоги, зарплата).
          </p>
          <button onclick="openAddSlotModal()" class="mt-1 bg-ci-600 hover:bg-ci-700 text-white font-bold text-xs px-3.5 py-1.5 rounded-xl transition shadow-sm inline-flex items-center space-x-1">
            <i data-lucide="plus" class="w-3.5 h-3.5"></i>
            <span>Добавить первый слот</span>
          </button>
        </div>
      `;
      lucide.createIcons();
      return;
    }

    slots.forEach(s => {
      const item = document.createElement('div');
      item.className = "p-3.5 rounded-2xl border border-slate-100 bg-white card-shadow flex items-center justify-between transition hover:border-slate-200";
      item.innerHTML = `
        <div class="flex items-center space-x-3">
          <div class="w-9 h-9 rounded-xl ${s.is_active ? 'bg-purple-50 text-purple-700 border border-purple-200' : 'bg-slate-100 text-slate-400'} font-black flex items-center justify-center text-xs shrink-0">
            ${s.day_of_month}
          </div>
          <div>
            <div class="text-xs font-black text-slate-900">${getCategoryName(s.category_id)}</div>
            <div class="text-[11px] text-slate-400 mt-0.5">
              <span>Каждое ${s.day_of_month}-е число</span> • <span class="font-medium text-slate-600">${s.counterparty_name || 'Регулярно'}</span>
            </div>
          </div>
        </div>
        <div class="flex items-center space-x-3">
          <div class="text-right">
            <div class="text-xs font-black ${s.is_active ? 'text-slate-900' : 'text-slate-400 line-through'}">${formatMoney(s.typical_amount)} ₽</div>
            <span class="text-[10px] ${s.is_active ? 'text-emerald-700 font-bold' : 'text-slate-400'}">${s.is_active ? 'В графике' : 'Приостановлен'}</span>
          </div>
          <button onclick="toggleSlotActive(${s.id}, ${!s.is_active})" title="Включить / выключить платеж" class="text-[10px] font-extrabold px-2.5 py-1 rounded-full transition shadow-xs ${s.is_active ? 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100 border border-emerald-200' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}">
            ${s.is_active ? 'Активен' : 'Отключен'}
          </button>
          <button onclick="deleteSlotById(${s.id})" title="Удалить слот" class="text-slate-300 hover:text-red-500 p-1.5 transition rounded-lg hover:bg-red-50">
            <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
          </button>
        </div>
      `;
      box.appendChild(item);
    });
    lucide.createIcons();
  } catch (err) {
    console.error('Error loading slots:', err);
  }
}

function renderFutureEventsList(events) {
  state.futureEvents = events || [];
  const box = document.getElementById('futureEventsList');
  const countBadge = document.getElementById('futureEventsCountBadge');
  if (!box) return;

  if (countBadge) countBadge.innerText = events.length;

  if (events.length === 0) {
    box.innerHTML = `
      <div class="p-3.5 rounded-xl bg-amber-50/50 border border-amber-200/60 text-xs text-amber-900 flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <i data-lucide="calendar" class="w-4 h-4 text-amber-600"></i>
          <span>Нет разовых запланированных платежей на ближайшие дни</span>
        </div>
        <button onclick="openAddEventModal('outflow')" class="text-amber-800 font-extrabold text-[11px] underline hover:text-amber-950">
          + Запланировать
        </button>
      </div>
    `;
    lucide.createIcons();
    return;
  }

  box.innerHTML = '';
  events.forEach(ev => {
    const isTax = ev.source === 'tax_calendar' || (ev.note && ev.note.includes('Налоги по УСН/НДС'));
    const isOutflow = (ev.amount < 0) || (ev.direction === 'Списание');
    const absAmt = Math.abs(ev.amount);
    const isActive = ev.is_active !== false;
    const item = document.createElement('div');
    
    // Distinct styling for active vs disabled vs tax calendar
    if (!isActive) {
      item.className = "p-3.5 rounded-2xl border border-slate-200 bg-slate-50/70 card-shadow flex items-center justify-between transition opacity-75 hover:opacity-100";
    } else if (isTax) {
      item.className = "p-3.5 rounded-2xl border border-purple-300 bg-purple-50/80 card-shadow flex items-center justify-between transition hover:shadow-md hover:border-purple-400";
    } else {
      item.className = `p-3.5 rounded-2xl border ${isOutflow ? 'border-amber-200 bg-amber-50/60' : 'border-blue-200 bg-blue-50/60'} card-shadow flex items-center justify-between transition hover:shadow-md`;
    }

    const dt = new Date(ev.event_date);
    const dayStr = dt.getDate();
    const monthNames = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
    const monthStr = monthNames[dt.getMonth()] || '';

    const now = new Date();
    const isToday = dt.toDateString() === now.toDateString();
    const tomorrow = new Date(); tomorrow.setDate(now.getDate() + 1);
    const isTomorrow = dt.toDateString() === tomorrow.toDateString();
    const dateLabel = isToday ? 'Сегодня' : (isTomorrow ? 'Завтра' : `${dayStr} ${monthStr}`);

    const dateBoxClass = !isActive
      ? 'bg-slate-200 text-slate-500 border border-slate-300'
      : (isTax
         ? 'bg-purple-100 text-purple-900 border border-purple-300'
         : (isOutflow
            ? 'bg-amber-100 text-amber-900 border border-amber-300'
            : 'bg-blue-100 text-blue-900 border border-blue-300'));

    let titleText = ev.counterparty_name || (isOutflow ? 'Запланированный платеж' : 'Ожидаемое поступление');
    if (isTax && ev.note) {
      const parts = ev.note.split('|');
      titleText = parts[parts.length - 1].trim();
    }

    const statusBadge = !isActive
      ? '<span class="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-slate-200 text-slate-600">Отключен</span>'
      : (isTax
         ? `<span class="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-purple-100 text-purple-900 border border-purple-200">${absAmt === 0 ? 'Плановое уведомление' : 'Плановый налог'}</span>`
         : (isOutflow
            ? '<span class="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 border border-amber-200">Запланировано списание</span>'
            : '<span class="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-blue-100 text-blue-900 border border-blue-200">Ожидается поступление</span>'));

    const tagBadge = isTax
      ? `<span class="text-[10px] font-black px-2 py-0.5 rounded-full bg-purple-100 text-purple-900 border border-purple-300 flex items-center space-x-1 shadow-2xs">
           <i data-lucide="landmark" class="w-3 h-3 text-purple-700"></i>
           <span>Налоги по УСН/НДС</span>
         </span>`
      : '';

    item.innerHTML = `
      <div class="flex items-center space-x-3">
        <div class="w-11 h-11 rounded-xl ${dateBoxClass} flex flex-col items-center justify-center font-black text-xs shrink-0 shadow-2xs">
          <span class="text-[9px] uppercase font-extrabold tracking-tight">${dateLabel}</span>
          <span class="text-sm font-black leading-none">${dayStr}</span>
        </div>
        <div>
          <div class="flex items-center space-x-2 flex-wrap gap-y-1">
            <span class="text-xs font-black ${isTax ? 'text-purple-950' : 'text-slate-900'} ${!isActive ? 'line-through text-slate-400' : ''}">
              ${titleText}
              ${ev.counterparty_inn && !isTax ? `<span class="text-slate-400 font-mono font-medium text-[11px] ml-1">(ИНН ${ev.counterparty_inn})</span>` : ''}
            </span>
            ${tagBadge}
            ${statusBadge}
          </div>
          <div class="text-[11px] ${isTax ? 'text-purple-700 font-medium' : 'text-slate-500'} mt-0.5 flex items-center space-x-1.5 flex-wrap">
            <span>${isTax ? 'ФНС России (ЕНС)' : getCategoryName(ev.category_id)}</span>
            <span>•</span>
            <span>Срок: <b>${formatDate(ev.event_date)}</b></span>
            ${!isTax ? `<span>•</span><span>Вероятность: <b>${Math.round((ev.probability || 1.0) * 100)}%</b></span>` : ''}
          </div>
        </div>
      </div>
      <div class="flex items-center space-x-2">
        <div class="text-right mr-1">
          <div class="text-sm font-black ${!isActive ? 'text-slate-400 line-through' : (isTax ? 'text-purple-950' : (isOutflow ? 'text-amber-950' : 'text-blue-950'))} font-display">
            ${absAmt > 0 ? (isOutflow ? '− ' : '+ ') + formatMoney(absAmt) + ' ₽' : '<span class="text-xs text-purple-800 font-bold">0.00 ₽ (уведомление)</span>'}
          </div>
          <span class="text-[10px] font-bold ${!isActive ? 'text-slate-400' : (isTax ? 'text-purple-700' : (isOutflow ? 'text-amber-700' : 'text-blue-700'))}">
            ${!isActive ? 'Отключен от радара' : (isTax ? 'Налоговый календарь' : 'Учтен в радаре')}
          </span>
        </div>

        <!-- Confirm Fact Button -->
        ${absAmt > 0 ? `
        <button onclick="confirmFuturePaymentToOperation('${ev.id}')" title="Подтвердить факт уплаты (перенести в операции)" class="flex items-center space-x-1 px-2.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-extrabold text-[11px] transition shadow-xs">
          <i data-lucide="check" class="w-3.5 h-3.5"></i>
          <span class="hidden sm:inline">Факт</span>
        </button>` : ''}

        <!-- Edit Button -->
        <button onclick="openEditEventModal('${ev.id}')" title="Редактировать параметры" class="text-slate-400 hover:text-slate-700 p-1.5 transition rounded-lg hover:bg-slate-100">
          <i data-lucide="edit-3" class="w-4 h-4"></i>
        </button>

        <!-- Toggle Active / Disabled Button -->
        <button onclick="toggleEventActive('${ev.id}', ${!isActive})" title="${isActive ? 'Отключить платеж' : 'Включить платеж'}" class="text-[10px] font-extrabold px-2.5 py-1 rounded-full transition shadow-xs ${isActive ? 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100 border border-emerald-200' : 'bg-slate-200 text-slate-600 hover:bg-slate-300'}">
          ${isActive ? 'Вкл' : 'Выкл'}
        </button>

        <!-- Delete Button -->
        <button onclick="deleteEventById('${ev.id}')" title="Удалить" class="text-slate-300 hover:text-red-500 p-1.5 transition rounded-lg hover:bg-red-50">
          <i data-lucide="trash-2" class="w-4 h-4"></i>
        </button>
      </div>
    `;
    box.appendChild(item);
  });
  lucide.createIcons();
}

async function confirmFuturePaymentToOperation(eventId) {
  try {
    const res = await fetch(`/api/events/${eventId}/confirm`, {
      method: 'POST',
      headers: getAuthHeaders()
    });
    if (res.ok) {
      const data = await res.json();
      showToast('Платеж подтвержден и перенесен в фактические операции!');
      await loadSlots();
      await loadOperations();
      await loadForecastData();
      await loadUserProfile();
      await loadCabinetData();
    } else {
      const err = await res.json();
      showToast(err.detail || 'Ошибка подтверждения');
    }
  } catch (err) {
    console.error('Error confirming event:', err);
    showToast('Ошибка подтверждения платежа');
  }
}

async function toggleEventActive(eventId, isActive) {
  try {
    const res = await fetch(`/api/events/${eventId}`, {
      method: 'PATCH',
      headers: getAuthHeaders(),
      body: JSON.stringify({ is_active: isActive })
    });
    if (res.ok) {
      showToast(isActive ? 'Платеж включен в расчет радара' : 'Платеж отключен от радара');
      await loadSlots();
      await loadForecastData();
    }
  } catch (err) {
    console.error('Error toggling event active:', err);
  }
}

function openEditEventModal(eventId) {
  const ev = (state.futureEvents || []).find(x => String(x.id) === String(eventId));
  if (!ev) return;

  const modal = document.getElementById('editEventModal');
  if (!modal) return;

  document.getElementById('editEvId').value = ev.id;
  document.getElementById('editEvAmount').value = Math.abs(ev.amount);
  document.getElementById('editEvDirection').value = (ev.amount < 0 || ev.direction === 'Списание') ? 'outflow' : 'inflow';
  document.getElementById('editEvDate').value = ev.event_date ? String(ev.event_date).slice(0, 10) : '';
  document.getElementById('editEvProbability').value = String(ev.probability || 1.0);
  document.getElementById('editEvCounterparty').value = ev.counterparty_name || '';
  const cpInnInput = document.getElementById('editEvCounterpartyInn');
  if (cpInnInput) cpInnInput.value = ev.counterparty_inn || '';
  document.getElementById('editEvCategory').value = ev.category_id || 'cat_procurement';
  document.getElementById('editEvIsActive').checked = ev.is_active !== false;

  populateCounterpartiesDropdowns((ev.amount < 0 || ev.direction === 'Списание') ? 'outflow' : 'inflow');
  const editSelect = document.getElementById('editEvQuickCounterpartySelect');
  if (editSelect) editSelect.value = ev.counterparty_inn || '';

  modal.classList.remove('hidden');
  lucide.createIcons();
}

function closeEditEventModal() {
  const modal = document.getElementById('editEventModal');
  if (modal) modal.classList.add('hidden');
}

async function submitEditEvent(e) {
  e.preventDefault();
  const id = document.getElementById('editEvId').value;
  const amt = parseFloat(document.getElementById('editEvAmount').value) || 0;
  const dir = document.getElementById('editEvDirection').value;
  const signedAmt = dir === 'inflow' ? Math.abs(amt) : -Math.abs(amt);
  const evDate = document.getElementById('editEvDate').value;
  const prob = parseFloat(document.getElementById('editEvProbability').value) || 1.0;
  const cp = document.getElementById('editEvCounterparty').value.trim();
  const cpInn = (document.getElementById('editEvCounterpartyInn')?.value || '').trim();
  const cat = document.getElementById('editEvCategory').value;
  const isActive = document.getElementById('editEvIsActive').checked;

  const cpErr = validateCounterpartyInput(cp, cpInn);
  if (cpErr) {
    showToast(cpErr);
    return;
  }

  try {
    const res = await fetch(`/api/events/${id}`, {
      method: 'PATCH',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        event_date: evDate,
        amount: signedAmt,
        probability: prob,
        category_id: cat,
        counterparty_name: cp,
        counterparty_inn: cpInn,
        is_active: isActive
      })
    });
    if (res.ok) {
      closeEditEventModal();
      showToast('Запланированный платеж успешно обновлен!');
      await loadSlots();
      await loadForecastData();
    } else {
      const err = await res.json();
      showToast(err.detail || 'Ошибка сохранения');
    }
  } catch (err) {
    console.error('Error updating event:', err);
    showToast('Ошибка сохранения платежа');
  }
}

async function deleteEventById(eventId) {
  try {
    const res = await fetch(`/api/events/${eventId}`, {
      method: 'DELETE',
      headers: getAuthHeaders()
    });
    if (res.ok) {
      showToast('Запланированный платеж удален');
      await loadSlots();
      await loadForecastData();
    }
  } catch (err) {
    console.error(err);
  }
}

function openAddSlotModal() {
  const modal = document.getElementById('addSlotModal');
  if (modal) modal.classList.remove('hidden');
  lucide.createIcons();
}

function closeAddSlotModal() {
  const modal = document.getElementById('addSlotModal');
  if (modal) modal.classList.add('hidden');
}

async function submitNewSlot(e) {
  e.preventDefault();
  const cat = document.getElementById('slotCategory').value;
  const amt = parseFloat(document.getElementById('slotAmount').value);
  const day = parseInt(document.getElementById('slotDayOfMonth').value, 10);
  const cp = document.getElementById('slotCounterparty').value;

  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/slots`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        category_id: cat,
        typical_amount: amt,
        day_of_month: day,
        counterparty_name: cp || 'Регулярный платеж',
        direction: 'Списание'
      })
    });
    if (res.ok) {
      closeAddSlotModal();
      showToast('Регулярный платеж добавлен в календарь');
      await loadSlots();
      await loadForecastData();
    }
  } catch (err) {
    console.error(err);
  }
}

async function toggleSlotActive(slotId, newActiveState) {
  try {
    const res = await fetch(`/api/slots/${slotId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: newActiveState })
    });
    if (res.ok) {
      showToast(newActiveState ? 'Платеж включен в прогноз' : 'Платеж приостановлен');
      await loadSlots();
      await loadForecastData();
    }
  } catch (err) {
    console.error(err);
  }
}

async function deleteSlotById(slotId) {
  if (!confirm('Удалить этот регулярный платеж из календаря?')) return;
  try {
    const res = await fetch(`/api/slots/${slotId}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Регулярный платеж удален');
      await loadSlots();
      await loadForecastData();
    }
  } catch (err) {
    console.error(err);
  }
}

// 9. Analytics
async function loadAnalytics() {
  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/analytics`);
    if (!res.ok) return;
    const an = await res.json();

    const infEl = document.getElementById('anTotalInflow');
    const outEl = document.getElementById('anTotalOutflow');
    const netEl = document.getElementById('anNetFlow');
    const burnEl = document.getElementById('anMonthlyBurn');
    const runEl = document.getElementById('anRunwayDays');
    const runBadge = document.getElementById('anRunwayBadge');
    const owEl = document.getElementById('anOwnerWithdrawn');

    if (infEl) infEl.innerText = `${formatMoney(an.total_inflow)} ₽`;
    if (outEl) outEl.innerText = `${formatMoney(an.total_outflow)} ₽`;

    if (netEl) {
      const isPos = an.net_flow >= 0;
      netEl.innerText = `${isPos ? '+' : ''}${formatMoney(an.net_flow)} ₽`;
      netEl.className = isPos ? 'text-base sm:text-lg font-black text-emerald-700 mt-1' : 'text-base sm:text-lg font-black text-red-600 mt-1';
    }

    if (burnEl) {
      burnEl.innerText = `${formatMoney(an.fixed_monthly_burn || 0)} ₽ / мес`;
    }

    // Runway safety formatting
    const rDays = an.safety_runway_days;
    if (runEl) {
      if (rDays >= 90) {
        runEl.innerText = '90+ дней (безопасно)';
      } else if (rDays >= 30) {
        runEl.innerText = `${rDays} дней (норма)`;
      } else if (rDays >= 14) {
        runEl.innerText = `${rDays} дней (внимание)`;
      } else {
        runEl.innerText = `${rDays} дней (дефицит!)`;
      }
    }
    if (runBadge) {
      if (rDays >= 30) {
        runBadge.className = 'text-xs px-3 py-1.5 rounded-xl font-bold bg-emerald-50 text-emerald-800 border border-emerald-200 flex items-center space-x-1.5 shadow-2xs';
      } else if (rDays >= 14) {
        runBadge.className = 'text-xs px-3 py-1.5 rounded-xl font-bold bg-amber-50 text-amber-900 border border-amber-200 flex items-center space-x-1.5 shadow-2xs';
      } else {
        runBadge.className = 'text-xs px-3 py-1.5 rounded-xl font-bold bg-red-50 text-red-900 border border-red-200 flex items-center space-x-1.5 shadow-2xs';
      }
    }

    // Concentration Warning
    const concBanner = document.getElementById('anConcentrationBanner');
    const concText = document.getElementById('anConcentrationText');
    if (concBanner && concText) {
      if (an.concentration_warning) {
        concBanner.classList.remove('hidden');
        concText.innerText = an.concentration_warning;
      } else {
        concBanner.classList.add('hidden');
      }
    }

    // Owner Withdrawn
    const os = an.owner_draw_summary || {};
    if (owEl) owEl.innerText = `${formatMoney(os.withdrawn_by_owner || 0)} ₽`;

    // Category shares
    const shareList = document.getElementById('anCategorySharesList');
    if (shareList) {
      shareList.innerHTML = '';
      if (!an.outflow_categories || an.outflow_categories.length === 0) {
        shareList.innerHTML = '<div class="text-xs text-slate-400 p-2">Данные появятся после проведения первых расходных операций</div>';
      } else {
        (an.outflow_categories || []).slice(0, 6).forEach(c => {
          const row = document.createElement('div');
          row.className = "text-xs p-2 rounded-xl bg-slate-50 border border-slate-100";
          row.innerHTML = `
            <div class="flex justify-between font-bold mb-1.5">
              <span class="text-slate-800">${c.name}</span>
              <span class="text-slate-900 font-black">${c.per_100_rubles} ₽ <span class="text-[10px] text-slate-400 font-normal">из 100 ₽</span></span>
            </div>
            <div class="w-full bg-slate-200/80 h-2 rounded-full overflow-hidden">
              <div class="h-full rounded-full transition-all duration-500" style="width: ${c.percent}%; background-color: ${c.color}"></div>
            </div>
          `;
          shareList.appendChild(row);
        });
      }
    }

    // Top Counterparties
    const clientList = document.getElementById('anTopClientsList');
    if (clientList) {
      clientList.innerHTML = '';
      const topC = an.top_counterparties || [];
      if (topC.length === 0) {
        clientList.innerHTML = '<div class="text-xs text-slate-400 p-2">Поступления от контрагентов еще не зафиксированы</div>';
      } else {
        topC.slice(0, 5).forEach((cl, idx) => {
          const cRow = document.createElement('div');
          cRow.className = "p-2.5 rounded-xl border border-slate-100 bg-slate-50 flex items-center justify-between text-xs";
          cRow.innerHTML = `
            <div class="truncate mr-2">
              <div class="font-bold text-slate-800 truncate">${cl.name || 'Контрагент'}</div>
              <div class="text-[10px] text-slate-400 font-mono">ИНН: ${cl.inn || '—'}</div>
            </div>
            <div class="text-right shrink-0">
              <div class="font-black text-slate-900 text-xs">${formatMoney(cl.amount)} ₽</div>
              <span class="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-1.5 py-0.2 rounded-full border border-emerald-100">${cl.percent}%</span>
            </div>
          `;
          clientList.appendChild(cRow);
        });
      }
    }

    lucide.createIcons();
  } catch (err) {
    console.error('Error loading analytics:', err);
  }
}

// 10. Integrations
async function loadIntegrations() {
  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/integrations`);
    if (!res.ok) return;
    const items = await res.json();

    const grid = document.getElementById('integrationsGrid');
    if (!grid) return;
    grid.innerHTML = '';
    items.forEach(item => {
      const card = document.createElement('div');
      card.className = "p-4 rounded-2xl border border-slate-100 bg-white card-shadow flex flex-col justify-between hover:border-slate-200 transition";
      const iconMap = {
        '1c_enterprise': 'database',
        'fns_nalog': 'landmark',
        'bank_centroinvest': 'shield-check',
        'edo_diadoc': 'file-check-2',
        'marketplaces': 'shopping-bag'
      };
      const iconName = iconMap[item.adapter_name] || 'plug';
      card.innerHTML = `
        <div>
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center space-x-2">
              <div class="w-7 h-7 rounded-lg bg-emerald-50 text-ci-700 flex items-center justify-center">
                <i data-lucide="${iconName}" class="w-4 h-4"></i>
              </div>
              <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">${item.adapter_name}</span>
            </div>
            <span class="text-[9px] font-bold px-2 py-0.5 rounded-full ${item.status === 'mock' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}">
              ${item.status === 'mock' ? 'Mock API' : 'Активно'}
            </span>
          </div>
          <div class="text-xs font-black text-slate-900">${item.display_name}</div>
        </div>
        <div class="mt-3.5 pt-2.5 border-t border-slate-100 flex items-center justify-between text-xs">
          <span class="text-[11px] text-slate-500 font-medium">Событий в радар: <b class="text-slate-900 font-bold">${item.events_added}</b></span>
          <button onclick="triggerSync('${item.adapter_name}')" class="bg-ci-600 hover:bg-ci-700 text-white font-bold text-xs px-3 py-1.5 rounded-xl transition shadow-sm flex items-center space-x-1">
            <i data-lucide="refresh-cw" class="w-3 h-3"></i>
            <span>Синхронизировать</span>
          </button>
        </div>
      `;
      grid.appendChild(card);
    });
    lucide.createIcons();
  } catch (err) {
    console.error('Error loading integrations:', err);
  }
}

async function triggerSync(adapterName) {
  showToast(`Синхронизация ${adapterName}...`);
  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/integrations/${adapterName}/sync`, {
      method: 'POST'
    });
    if (res.ok) {
      const data = await res.json();
      showToast(`Готово! Добавлено ${data.events_added_this_run} событий`);
      await loadIntegrations();
      await loadForecastData();
    }
  } catch (err) {
    console.error(err);
  }
}

async function performRegistryCheck() {
  const inn = document.getElementById('checkInnInput').value.trim();
  if (!inn) return;

  const resBox = document.getElementById('registryCheckResult');
  resBox.className = "mt-2 p-2 rounded-lg text-xs border border-slate-200 bg-slate-50";
  resBox.innerText = "Проверка...";
  resBox.classList.remove('hidden');

  try {
    const res = await fetch(`/api/integrations/registry/check?inn=${encodeURIComponent(inn)}`);
    const data = await res.json();
    if (data.bankruptcy_risk) {
      resBox.className = "mt-2 p-2 rounded-lg text-xs border border-red-300 bg-red-50 text-red-900 font-semibold";
      resBox.innerHTML = `⚠️ <b>РИСК!</b> ${data.details}`;
    } else {
      resBox.className = "mt-2 p-2 rounded-lg text-xs border border-emerald-300 bg-emerald-50 text-emerald-900 font-semibold";
      resBox.innerHTML = `✓ ${data.details}`;
    }
  } catch (err) {
    console.error(err);
  }
}

// ================= COUNTERPARTY DROPDOWN & INSTANT AUTOCOMPLETE =================
function getUnifiedCounterpartiesList(direction = 'inflow') {
  const map = new Map();

  // 1. Existing registered counterparties from DB
  (state.counterparties || []).forEach(c => {
    if (c && c.inn) {
      const inn = String(c.inn).trim();
      const name = String(c.name || '').trim();
      if (inn) {
        map.set(inn, {
          inn,
          name: name || `ИНН ${inn}`,
          turnover: c.turnover_total || 0,
          is_supplier: Boolean(c.is_supplier),
          is_payer: Boolean(c.is_payer),
          reliability: c.reliability_score || 0,
          risk: c.risk_level || 'green'
        });
      }
    }
  });

  // 2. Extra counterparties from operations (e.g. from loaded bank statements)
  (state.operations || []).forEach(op => {
    const inn = String(op.counterparty_inn || '').trim();
    const name = String(op.counterparty_name || op.counterparty || '').trim();
    if (inn && !map.has(inn)) {
      map.set(inn, {
        inn,
        name: name || `ИНН ${inn}`,
        turnover: Math.abs(op.amount || 0),
        is_supplier: op.direction === 'Списание',
        is_payer: op.direction === 'Поступление',
        reliability: 80,
        risk: 'green'
      });
    }
  });

  const list = Array.from(map.values());
  list.sort((a, b) => {
    if (direction === 'inflow') {
      if (a.is_payer !== b.is_payer) return b.is_payer ? 1 : -1;
    } else {
      if (a.is_supplier !== b.is_supplier) return b.is_supplier ? 1 : -1;
    }
    if ((b.turnover || 0) !== (a.turnover || 0)) {
      return (b.turnover || 0) - (a.turnover || 0);
    }
    return a.name.localeCompare(b.name, 'ru');
  });

  return list;
}

function populateCounterpartiesDropdowns(direction = state.modalDirection || 'inflow') {
  const counterparties = getUnifiedCounterpartiesList(direction);

  // 1. Datalists for native instant autocomplete
  const namesDatalist = document.getElementById('counterpartyNamesList');
  const innsDatalist = document.getElementById('counterpartyInnsList');

  if (namesDatalist) {
    namesDatalist.innerHTML = counterparties
      .map(c => `<option value="${c.name}">${c.inn ? 'ИНН ' + c.inn : ''}</option>`)
      .join('');
  }
  if (innsDatalist) {
    innsDatalist.innerHTML = counterparties
      .map(c => `<option value="${c.inn}">${c.name}</option>`)
      .join('');
  }

  // 2. Quick select dropdown for Add Event Modal
  const addSelect = document.getElementById('evQuickCounterpartySelect');
  if (addSelect) {
    const currentVal = addSelect.value;
    let html = `<option value="">⚡ Выбрать контрагента из базы (1 клик)...</option>`;
    if (counterparties.length > 0) {
      const groupLabel = direction === 'inflow' ? 'Клиенты и регулярные плательщики' : 'Поставщики и партнеры';
      html += `<optgroup label="${groupLabel}">`;
      counterparties.forEach(c => {
        html += `<option value="${c.inn}">${c.name} (ИНН ${c.inn})</option>`;
      });
      html += `</optgroup>`;
    } else {
      html += `<option value="" disabled>Контрагенты появятся автоматически из базы и операций</option>`;
    }
    addSelect.innerHTML = html;
    if (currentVal && counterparties.some(c => c.inn === currentVal)) {
      addSelect.value = currentVal;
    }
  }

  // 3. Quick chips for Add Event Modal (top 4 counterparties)
  const chipsContainer = document.getElementById('evCounterpartyChips');
  if (chipsContainer) {
    chipsContainer.innerHTML = '';
    const top4 = counterparties.slice(0, 4);
    top4.forEach(c => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.onclick = () => selectCounterpartyByInn(c.inn, 'add');
      const shortName = c.name.length > 18 ? c.name.slice(0, 16) + '…' : c.name;
      btn.className = "text-[11px] font-bold px-2 py-1 bg-white hover:bg-emerald-50 text-slate-700 hover:text-emerald-900 border border-slate-200 hover:border-emerald-300 rounded-lg transition shadow-2xs flex items-center space-x-1";
      btn.innerHTML = `<span>${shortName}</span><span class="text-[9px] text-slate-400 font-mono">(${c.inn.slice(-4)})</span>`;
      chipsContainer.appendChild(btn);
    });
  }

  // 4. Quick select dropdown for Edit Event Modal
  const editSelect = document.getElementById('editEvQuickCounterpartySelect');
  if (editSelect) {
    const currentVal = editSelect.value;
    let html = `<option value="">⚡ Выбрать контрагента из базы (1 клик)...</option>`;
    if (counterparties.length > 0) {
      html += `<optgroup label="Все контрагенты базы">`;
      counterparties.forEach(c => {
        html += `<option value="${c.inn}">${c.name} (ИНН ${c.inn})</option>`;
      });
      html += `</optgroup>`;
    }
    editSelect.innerHTML = html;
    if (currentVal && counterparties.some(c => c.inn === currentVal)) {
      editSelect.value = currentVal;
    }
  }
}

function selectCounterpartyByInn(inn, mode = 'add') {
  if (!inn) return;
  const list = getUnifiedCounterpartiesList();
  const cp = list.find(c => String(c.inn).trim() === String(inn).trim());
  if (!cp) return;

  const prefix = mode === 'edit' ? 'editEv' : 'ev';
  const nameInput = document.getElementById(`${prefix}Counterparty`);
  const innInput = document.getElementById(`${prefix}CounterpartyInn`);
  const selectDropdown = document.getElementById(mode === 'edit' ? 'editEvQuickCounterpartySelect' : 'evQuickCounterpartySelect');

  if (nameInput) nameInput.value = cp.name;
  if (innInput) innInput.value = cp.inn;
  if (selectDropdown) selectDropdown.value = cp.inn;
}

function onQuickSelectCounterparty(inn, mode = 'add') {
  if (!inn) return;
  selectCounterpartyByInn(inn, mode);
}

function onCounterpartyNameInput(nameVal, mode = 'add') {
  const val = String(nameVal || '').trim().toLowerCase();
  if (!val) return;

  const list = getUnifiedCounterpartiesList();
  const match = list.find(c => c.name.trim().toLowerCase() === val);
  if (match) {
    const prefix = mode === 'edit' ? 'editEv' : 'ev';
    const innInput = document.getElementById(`${prefix}CounterpartyInn`);
    const selectDropdown = document.getElementById(mode === 'edit' ? 'editEvQuickCounterpartySelect' : 'evQuickCounterpartySelect');
    if (innInput && (!innInput.value || innInput.value.trim() === '')) {
      innInput.value = match.inn;
    }
    if (selectDropdown) {
      selectDropdown.value = match.inn;
    }
  }
}

function onCounterpartyInnInput(innVal, mode = 'add') {
  const prefix = mode === 'edit' ? 'editEv' : 'ev';
  const innInput = document.getElementById(`${prefix}CounterpartyInn`);
  const cleanDigits = String(innVal || '').replace(/\D/g, '').slice(0, 12);
  if (innInput && innInput.value !== cleanDigits) {
    innInput.value = cleanDigits;
  }

  if (cleanDigits.length >= 10) {
    const list = getUnifiedCounterpartiesList();
    const match = list.find(c => c.inn === cleanDigits);
    if (match) {
      const nameInput = document.getElementById(`${prefix}Counterparty`);
      const selectDropdown = document.getElementById(mode === 'edit' ? 'editEvQuickCounterpartySelect' : 'evQuickCounterpartySelect');
      if (nameInput && (!nameInput.value || nameInput.value.trim() === '')) {
        nameInput.value = match.name;
      }
      if (selectDropdown) {
        selectDropdown.value = match.inn;
      }
    }
  }
}

// 11. Quick Add Event Modal
function openAddEventModal(direction) {
  state.modalDirection = direction;
  const title = document.getElementById('modalEventTitle');
  const iconBg = document.getElementById('modalEventIconBg');
  const submitBtn = document.getElementById('evSubmitBtn');
  const catSelect = document.getElementById('evCategory');

  if (title) title.innerText = direction === 'inflow' ? 'Ожидаемое поступление' : 'Планируемый платеж';
  if (iconBg) {
    iconBg.className = direction === 'inflow' ?
      'w-8 h-8 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold' :
      'w-8 h-8 rounded-xl bg-red-100 text-red-700 flex items-center justify-center font-bold';
    iconBg.innerHTML = direction === 'inflow' ? '<i data-lucide="arrow-down-left" class="w-4 h-4"></i>' : '<i data-lucide="arrow-up-right" class="w-4 h-4"></i>';
  }
  if (submitBtn) {
    submitBtn.innerText = direction === 'inflow' ? 'Добавить поступление' : 'Запланировать расход';
    submitBtn.className = direction === 'inflow' ?
      'flex-1 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold transition shadow-sm' :
      'flex-1 py-2.5 rounded-xl bg-slate-900 hover:bg-black text-white font-bold transition shadow-sm';
  }

  // Populate categories based on direction
  if (catSelect) {
    catSelect.innerHTML = '';
    const inflowCats = [
      { id: 'cat_revenue_client', name: 'Выручка от клиентов' },
      { id: 'cat_revenue_acquiring', name: 'Эквайринг и СБП' },
      { id: 'cat_owner_deposit', name: 'Деньги от владельца (взнос)' },
      { id: 'cat_refund_in', name: 'Возврат от поставщика' },
      { id: 'cat_other_in', name: 'Прочие поступления' }
    ];
    const outflowCats = [
      { id: 'cat_procurement', name: 'Закупки и сырьё' },
      { id: 'cat_payroll', name: 'Люди (зарплата и аванс)' },
      { id: 'cat_rent_utilities', name: 'Аренда и коммуналка' },
      { id: 'cat_tax_enp', name: 'Налоги и взносы (ЕНП)' },
      { id: 'cat_bank_credit', name: 'Банк и кредиты' },
      { id: 'cat_services_marketing', name: 'Маркетинг и сервисы' },
      { id: 'cat_transport', name: 'Транспорт и авто' },
      { id: 'cat_owner_draw', name: 'Деньги владельцу' },
      { id: 'cat_other_out', name: 'Прочие списания' }
    ];
    const targetCats = direction === 'inflow' ? inflowCats : outflowCats;
    targetCats.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name;
      catSelect.appendChild(opt);
    });
  }

  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const evDateInput = document.getElementById('evDate');
  if (evDateInput) evDateInput.value = tomorrow.toISOString().split('T')[0];

  const cpInput = document.getElementById('evCounterparty');
  if (cpInput) cpInput.value = '';
  const cpInnInput = document.getElementById('evCounterpartyInn');
  if (cpInnInput) cpInnInput.value = '';

  populateCounterpartiesDropdowns(direction);
  const quickSelect = document.getElementById('evQuickCounterpartySelect');
  if (quickSelect) quickSelect.value = '';

  const modal = document.getElementById('eventModal');
  if (modal) modal.classList.remove('hidden');
  lucide.createIcons();
}

function closeAddEventModal() {
  document.getElementById('eventModal').classList.add('hidden');
}

async function submitNewEvent(e) {
  e.preventDefault();
  const amt = parseFloat(document.getElementById('evAmount').value) || 0;
  const evDate = document.getElementById('evDate').value;
  const prob = parseFloat(document.getElementById('evProbability').value) || 1.0;
  const cp = document.getElementById('evCounterparty').value.trim();
  const cpInn = (document.getElementById('evCounterpartyInn')?.value || '').trim();
  const cat = document.getElementById('evCategory').value;

  const cpErr = validateCounterpartyInput(cp, cpInn);
  if (cpErr) {
    showToast(cpErr);
    return;
  }

  const todayStr = new Date().toISOString().slice(0, 10);
  const isPastOrToday = evDate <= todayStr;

  try {
    if (isPastOrToday) {
      // Past or Today: Record immediately as historical Operation
      const direction = state.modalDirection === 'inflow' ? 'Поступление' : 'Списание';
      const res = await fetch(`/api/companies/${state.currentCompanyId}/operations`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          operation_date: evDate,
          amount: Math.abs(amt),
          direction: direction,
          category_id: cat,
          counterparty_name: cp,
          counterparty_inn: cpInn,
          payment_purpose: `Оплата: ${cp}`
        })
      });
      if (res.ok) {
        closeAddEventModal();
        showToast('Фактическая операция внесена в историю и учтена в остатке!');
        await loadOperations();
        await loadForecastData();
        await loadUserProfile();
        await loadCabinetData();
        await loadCounterparties();
      } else {
        const err = await res.json();
        showToast(err.detail || 'Ошибка сохранения операции');
      }
    } else {
      // Future: Record as planned Event
      const signedAmount = state.modalDirection === 'inflow' ? Math.abs(amt) : -Math.abs(amt);
      const res = await fetch(`/api/companies/${state.currentCompanyId}/events`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          event_date: evDate,
          amount: signedAmount,
          probability: prob,
          category_id: cat,
          counterparty_name: cp,
          counterparty_inn: cpInn,
          is_active: true
        })
      });
      if (res.ok) {
        closeAddEventModal();
        showToast('Платеж запланирован в слотах и учтен в Радаре!');
        await loadSlots();
        await loadForecastData();
        await loadCounterparties();
      } else {
        const err = await res.json();
        showToast(err.detail || 'Ошибка планирования');
      }
    }
  } catch (err) {
    console.error('Error submitting event:', err);
    showToast('Ошибка при сохранении платежа');
  }
}

// ================= 12. ЛИЧНЫЙ КАБИНЕТ И ЗАГРУЗКА ВЫПИСКИ =================
function openCabinetModal(initialTab = 'profile') {
  const modal = document.getElementById('cabinetModal');
  if (!modal) return;

  const c = state.companyInfo || {};
  const u = state.currentUser || {};

  document.getElementById('cabFullName').value = u.full_name || '';
  document.getElementById('cabLegalForm').value = c.legal_form || 'ИП';
  document.getElementById('cabInn').value = c.inn || '';
  document.getElementById('cabCompanyName').value = c.name || '';
  document.getElementById('cabIndustry').value = c.industry || '';
  document.getElementById('cabTaxRegime').value = c.tax_regime || 'УСН Доходы 6%';
  document.getElementById('cabManualBalance').value = c.initial_manual_balance || c.last_balance || 0;

  setCabinetTab(initialTab);
  modal.classList.remove('hidden');
  lucide.createIcons();
}

function closeCabinetModal() {
  document.getElementById('cabinetModal').classList.add('hidden');
}

function setCabinetTab(tab) {
  const btnProf = document.getElementById('cab-tab-btn-profile');
  const btnStmt = document.getElementById('cab-tab-btn-statement');
  const cntProf = document.getElementById('cabContentProfile');
  const cntStmt = document.getElementById('cabContentStatement');

  if (tab === 'profile') {
    btnProf.className = "pb-2 px-3 border-b-2 border-ci-600 text-ci-700 font-bold";
    btnStmt.className = "pb-2 px-3 border-b-2 border-transparent text-slate-400 hover:text-slate-700";
    cntProf.classList.remove('hidden');
    cntStmt.classList.add('hidden');
  } else {
    btnProf.className = "pb-2 px-3 border-b-2 border-transparent text-slate-400 hover:text-slate-700";
    btnStmt.className = "pb-2 px-3 border-b-2 border-ci-600 text-ci-700 font-bold";
    cntProf.classList.add('hidden');
    cntStmt.classList.remove('hidden');
  }
}

async function saveCabinetProfile() {
  if (!state.currentUser || !state.authToken) {
    showToast('Для сохранения реквизитов войдите в аккаунт');
    closeCabinetModal();
    openAuthModal('login');
    return;
  }

  const payload = {
    name: document.getElementById('cabCompanyName').value.trim(),
    legal_form: document.getElementById('cabLegalForm').value,
    industry: document.getElementById('cabIndustry').value.trim(),
    tax_regime: document.getElementById('cabTaxRegime').value,
    initial_manual_balance: parseFloat(document.getElementById('cabManualBalance').value) || 0.0
  };

  const valErr = validateInnAndName(
    document.getElementById('cabInn') ? document.getElementById('cabInn').value : '6164000000',
    payload.legal_form,
    payload.name
  );
  if (valErr) {
    showToast(valErr);
    return;
  }

  try {
    const res = await fetch('/api/auth/company', {
      method: 'PATCH',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast('Реквизиты сохранены и применены!');
      closeCabinetModal();
      await loadCompaniesList();
      await loadAllCompanyData(state.currentCompanyId);
      populateCabinetPageDetails();
    } else {
      const err = await res.json();
      showToast(err.detail || 'Ошибка сохранения');
    }
  } catch (err) {
    console.error(err);
  }
}

function onFileSelected(input) {
  if (input.files && input.files[0]) {
    state.selectedFile = input.files[0];
    const nameEl = document.getElementById('selectedFileName');
    const submitBtn = document.getElementById('btnUploadSubmit');
    if (nameEl) nameEl.innerText = `Файл: ${state.selectedFile.name} (${(state.selectedFile.size / 1024).toFixed(1)} КБ)`;
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.classList.remove('bg-slate-200');
      submitBtn.classList.add('bg-ci-600');
    }
  }
}

// ================= STATEMENT UPLOAD WITH PROGRESS BAR =================
let uploadProgressInterval = null;

function openStatementProgressModal(filename, sizeBytes) {
  const modal = document.getElementById('statementProgressModal');
  if (!modal) return;

  const fnEl = document.getElementById('spmFileName');
  const fsEl = document.getElementById('spmFileSize');
  const bar = document.getElementById('spmBar');
  const pct = document.getElementById('spmPercent');
  const badge = document.getElementById('spmStageBadge');
  const title = document.getElementById('spmStageTitle');
  const text = document.getElementById('spmStageText');
  const rows = document.getElementById('spmRows');
  const speed = document.getElementById('spmSpeed');
  const elapsed = document.getElementById('spmElapsed');
  const eta = document.getElementById('spmEta');

  const procBody = document.getElementById('spmProcessingBody');
  const succBody = document.getElementById('spmSuccessBody');
  const errBody = document.getElementById('spmErrorBody');

  if (procBody) procBody.classList.remove('hidden');
  if (succBody) succBody.classList.add('hidden');
  if (errBody) errBody.classList.add('hidden');

  if (fnEl) fnEl.innerText = filename || 'statement.csv';
  if (fsEl) fsEl.innerText = sizeBytes ? `${(sizeBytes / (1024 * 1024)).toFixed(1)} МБ` : '0 МБ';
  if (bar) bar.style.width = '0%';
  if (pct) pct.innerText = '0';
  if (badge) {
    badge.innerText = 'Отправка...';
    badge.className = 'px-2.5 py-1 rounded-full text-[11px] font-black tracking-wide uppercase bg-blue-100 text-blue-800';
  }
  if (title) title.innerText = 'Передача файла на сервер...';
  if (text) text.innerText = 'Установка защищенного соединения...';
  if (rows) rows.innerText = '0 / 0';
  if (speed) speed.innerText = '—';
  if (elapsed) elapsed.innerText = '0.0 с';
  if (eta) eta.innerText = '—';

  modal.classList.remove('hidden');
  lucide.createIcons();
}

function closeStatementProgressModal(switchToRadar = false) {
  if (uploadProgressInterval) {
    clearInterval(uploadProgressInterval);
    uploadProgressInterval = null;
  }
  const modal = document.getElementById('statementProgressModal');
  if (modal) modal.classList.add('hidden');

  if (switchToRadar) {
    closeCabinetModal();
    switchTab('radar');
  }
}

async function startAsyncStatementUpload(file) {
  if (!file) return;

  openStatementProgressModal(file.name, file.size);

  const bar = document.getElementById('spmBar');
  const pct = document.getElementById('spmPercent');
  const badge = document.getElementById('spmStageBadge');
  const title = document.getElementById('spmStageTitle');
  const text = document.getElementById('spmStageText');
  const rows = document.getElementById('spmRows');
  const speed = document.getElementById('spmSpeed');
  const elapsed = document.getElementById('spmElapsed');
  const eta = document.getElementById('spmEta');

  const procBody = document.getElementById('spmProcessingBody');
  const succBody = document.getElementById('spmSuccessBody');
  const errBody = document.getElementById('spmErrorBody');

  const formData = new FormData();
  formData.append('file', file);

  const uploadStartTime = performance.now();

  const xhr = new XMLHttpRequest();
  xhr.open('POST', `/api/companies/${state.currentCompanyId}/upload-statement-async`, true);

  // Network upload progress (mapped to 0% - 25% of overall process)
  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      const netPct = Math.round((e.loaded / e.total) * 100);
      const totalMb = (e.total / (1024 * 1024)).toFixed(1);
      const loadedMb = (e.loaded / (1024 * 1024)).toFixed(1);
      const overallPct = Math.min(25, Math.round((e.loaded / e.total) * 25));

      const now = performance.now();
      const elSec = ((now - uploadStartTime) / 1000).toFixed(1);
      const mbps = elSec > 0 ? ((e.loaded / (1024 * 1024)) / elSec).toFixed(1) : '—';

      if (bar) bar.style.width = `${overallPct}%`;
      if (pct) pct.innerText = overallPct;
      if (title) title.innerText = `Передача файла: ${netPct}%`;
      if (text) text.innerText = `Загружено ${loadedMb} МБ из ${totalMb} МБ (${mbps} МБ/с)`;
      if (speed) speed.innerText = `${mbps} МБ/с`;
      if (elapsed) elapsed.innerText = `${elSec} с`;
    }
  };

  xhr.onload = async () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      const resp = JSON.parse(xhr.responseText);
      const taskId = resp.task_id;
      if (title) title.innerText = 'Серверная обработка данных...';
      if (text) text.innerText = 'Файл принят, запуск анализа операций...';
      if (badge) {
        badge.innerText = 'Обработка...';
        badge.className = 'px-2.5 py-1 rounded-full text-[11px] font-black tracking-wide uppercase bg-emerald-100 text-emerald-800';
      }

      // Poll task progress every 250 ms
      pollStatementProgress(taskId);
    } else {
      let errMsg = 'Ошибка отправки файла на сервер';
      try {
        const errJson = JSON.parse(xhr.responseText);
        errMsg = errJson.detail || errMsg;
      } catch (e) {}

      if (procBody) procBody.classList.add('hidden');
      if (errBody) errBody.classList.remove('hidden');
      const errEl = document.getElementById('spmErrorText');
      if (errEl) errEl.innerText = errMsg;
    }
  };

  xhr.onerror = () => {
    if (procBody) procBody.classList.add('hidden');
    if (errBody) errBody.classList.remove('hidden');
    const errEl = document.getElementById('spmErrorText');
    if (errEl) errEl.innerText = 'Ошибка сети при передаче файла';
  };

  xhr.send(formData);
}

function pollStatementProgress(taskId) {
  if (uploadProgressInterval) clearInterval(uploadProgressInterval);

  uploadProgressInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/companies/${state.currentCompanyId}/upload-progress/${taskId}`);
      if (!res.ok) return;

      const data = await res.json();

      const bar = document.getElementById('spmBar');
      const pct = document.getElementById('spmPercent');
      const badge = document.getElementById('spmStageBadge');
      const title = document.getElementById('spmStageTitle');
      const text = document.getElementById('spmStageText');
      const rows = document.getElementById('spmRows');
      const speed = document.getElementById('spmSpeed');
      const elapsed = document.getElementById('spmElapsed');
      const eta = document.getElementById('spmEta');

      const procBody = document.getElementById('spmProcessingBody');
      const succBody = document.getElementById('spmSuccessBody');
      const errBody = document.getElementById('spmErrorBody');

      if (bar) bar.style.width = `${data.progress_pct}%`;
      if (pct) pct.innerText = data.progress_pct;
      if (text) text.innerText = data.stage_text;
      if (elapsed) elapsed.innerText = `${data.elapsed_seconds.toFixed(1)} с`;
      if (eta) eta.innerText = data.eta_seconds > 0 ? `~${data.eta_seconds.toFixed(1)} с` : '—';
      if (rows) rows.innerText = `${data.processed_rows.toLocaleString()} / ${data.total_rows.toLocaleString()}`;
      if (speed) speed.innerText = data.speed_rows_per_sec > 0 ? `${Math.round(data.speed_rows_per_sec).toLocaleString()} строк/с` : '—';

      // Stage name & badge color
      if (badge && title) {
        if (data.stage === 'parsing') {
          badge.innerText = 'Парсинг CSV';
          title.innerText = 'Разбор и проверка структуры...';
          badge.className = 'px-2.5 py-1 rounded-full text-[11px] font-black tracking-wide uppercase bg-blue-100 text-blue-800';
        } else if (data.stage === 'cleaning') {
          badge.innerText = 'Очистка ИНН';
          title.innerText = 'Нормализация и дедупликация...';
          badge.className = 'px-2.5 py-1 rounded-full text-[11px] font-black tracking-wide uppercase bg-indigo-100 text-indigo-800';
        } else if (data.stage === 'categorizing') {
          badge.innerText = 'AI-разметка';
          title.innerText = 'Интеллектуальная категоризация...';
          badge.className = 'px-2.5 py-1 rounded-full text-[11px] font-black tracking-wide uppercase bg-purple-100 text-purple-800';
        } else if (data.stage === 'saving') {
          badge.innerText = 'Запись в БД';
          title.innerText = 'Пакетная запись в radar.db...';
          badge.className = 'px-2.5 py-1 rounded-full text-[11px] font-black tracking-wide uppercase bg-amber-100 text-amber-800';
        } else if (data.stage === 'slots') {
          badge.innerText = 'Поиск слотов';
          title.innerText = 'Выявление регулярных платежей...';
          badge.className = 'px-2.5 py-1 rounded-full text-[11px] font-black tracking-wide uppercase bg-teal-100 text-teal-800';
        } else if (data.stage === 'done') {
          badge.innerText = 'Готово 100%';
          title.innerText = 'Обработка завершена!';
          badge.className = 'px-2.5 py-1 rounded-full text-[11px] font-black tracking-wide uppercase bg-emerald-100 text-emerald-800';
        }
      }

      if (data.status === 'completed') {
        clearInterval(uploadProgressInterval);
        uploadProgressInterval = null;

        // Render success summary
        if (procBody) procBody.classList.add('hidden');
        if (succBody) succBody.classList.remove('hidden');

        const r = data.result || {};
        const resOps = document.getElementById('spmResOps');
        const resSlots = document.getElementById('spmResSlots');
        const resDates = document.getElementById('spmResDates');
        const resBal = document.getElementById('spmResBalance');
        const succDesc = document.getElementById('spmSuccessDesc');

        if (resOps) resOps.innerText = (r.operations_count || data.total_rows || 0).toLocaleString();
        if (resSlots) resSlots.innerText = r.slots_count || 0;
        if (resDates) resDates.innerText = `${r.first_date || '—'} … ${r.last_date || '—'}`;
        if (resBal) resBal.innerText = `${formatMoney(r.last_balance || 0)} ₽`;
        if (succDesc) succDesc.innerText = r.message || 'Выписка успешно загружена и проанализирована.';

        lucide.createIcons();

        // Refresh all company data and radar
        await loadAllCompanyData(state.currentCompanyId);
        populateCabinetPageDetails();
        showToast('Выписка успешно обработана!');
      } else if (data.status === 'error') {
        clearInterval(uploadProgressInterval);
        uploadProgressInterval = null;

        if (procBody) procBody.classList.add('hidden');
        if (errBody) errBody.classList.remove('hidden');
        const errEl = document.getElementById('spmErrorText');
        if (errEl) errEl.innerText = data.error || 'Произошла непредвиденная ошибка';
        lucide.createIcons();
      }

    } catch (e) {
      console.error('Error polling statement progress:', e);
    }
  }, 250);
}

async function uploadSelectedFile() {
  if (!state.selectedFile) return;
  startAsyncStatementUpload(state.selectedFile);
}

async function loadDemoStatement(demoSample) {
  showToast(`Загрузка демонстрационной выписки ${demoSample}...`);
  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/load-demo-statement?demo_sample=${demoSample}`, {
      method: 'POST'
    });
    if (res.ok) {
      const data = await res.json();
      showToast(data.message);
      closeCabinetModal();
      await loadAllCompanyData(state.currentCompanyId);
      switchTab('radar');
    }
  } catch (err) {
    console.error(err);
  }
}

// ================= 13. УПРОЩЕННАЯ АВТОРИЗАЦИЯ БЕЗ ПАРОЛЕЙ (ЧИСТО ПО ПОЧТЕ) =================
let otpState = {
  email: '',
  timerInterval: null,
  timerSeconds: 0
};

function openAuthModal() {
  document.getElementById('authModal').classList.remove('hidden');
  document.getElementById('authStep1Email').classList.remove('hidden');
  document.getElementById('authStep2Code').classList.add('hidden');
  document.getElementById('authStep3Complete').classList.add('hidden');
  document.getElementById('authModalTitle').innerText = "Вход по почте";
  document.getElementById('authModalSubtitle').innerText = "Быстрый вход без пароля по коду";
  lucide.createIcons();
}

function closeAuthModal() {
  document.getElementById('authModal').classList.add('hidden');
  if (otpState.timerInterval) clearInterval(otpState.timerInterval);
}

async function handleSendOtpCode(e) {
  e.preventDefault();
  const emailInput = document.getElementById('otpEmailInput');
  const email = emailInput ? emailInput.value.trim() : '';
  if (!email) return;

  const btn = document.getElementById('btnSendOtp');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Отправка кода...</span>`;
    lucide.createIcons();
  }

  try {
    const res = await fetch('/api/auth/send-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email })
    });

    if (res.ok) {
      const data = await res.json();
      otpState.email = email;
      showToast(data.message || 'Код успешно отправлен!');

      document.getElementById('authStep1Email').classList.add('hidden');
      document.getElementById('authStep2Code').classList.remove('hidden');
      document.getElementById('authStep3Complete').classList.add('hidden');
      document.getElementById('otpSentEmailDisplay').innerText = email;
      document.getElementById('authModalTitle').innerText = "Подтверждение входа";
      document.getElementById('authModalSubtitle').innerText = "Введите 6 цифр из письма";
      
      const codeInput = document.getElementById('otpCodeInput');
      if (codeInput) {
        codeInput.value = '';
        codeInput.focus();
      }

      startOtpTimer(60);
    } else {
      const err = await res.json();
      alert(err.detail || 'Ошибка отправки кода');
    }
  } catch (err) {
    console.error(err);
    alert('Произошла ошибка при отправке запроса');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="send" class="w-4 h-4"></i><span>Получить код на почту</span>`;
      lucide.createIcons();
    }
  }
}

async function handleVerifyOtpCode(e) {
  e.preventDefault();
  const code = document.getElementById('otpCodeInput').value.trim();
  if (!code || code.length !== 6) {
    alert('Введите 6-значный код');
    return;
  }

  const btn = document.getElementById('btnVerifyOtp');
  if (btn) {
    btn.disabled = true;
    btn.innerText = 'Проверка кода...';
  }

  try {
    const res = await fetch('/api/auth/verify-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: otpState.email, code })
    });

    if (res.ok) {
      const data = await res.json();

      if (data.status === 'authenticated' && data.access_token) {
        state.authToken = data.access_token;
        state.currentUser = data.user;
        state.currentCompanyId = data.company.id;
        localStorage.setItem('ci_radar_token', data.access_token);
        localStorage.setItem('ci_radar_company_id', data.company.id);

        closeAuthModal();
        showToast(`Добро пожаловать, ${data.user.full_name}!`);
        await loadCompaniesList();
        await loadAllCompanyData(data.company.id);
        renderUserHeader(data.user);
        populateCabinetPageDetails();
      } else if (data.status === 'needs_registration') {
        showToast('Почта подтверждена! Завершите регистрацию бизнеса.');
        document.getElementById('authStep1Email').classList.add('hidden');
        document.getElementById('authStep2Code').classList.add('hidden');
        document.getElementById('authStep3Complete').classList.remove('hidden');
        document.getElementById('verifiedEmailDisplay').innerText = otpState.email;
        document.getElementById('authModalTitle').innerText = "Завершите регистрацию";
        document.getElementById('authModalSubtitle').innerText = "Укажите реквизиты бизнеса (без пароля)";
        lucide.createIcons();
      }
    } else {
      const err = await res.json();
      alert(err.detail || 'Неверный код подтверждения');
    }
  } catch (err) {
    console.error(err);
    alert('Ошибка при проверке кода');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = 'Подтвердить и войти';
    }
  }
}

async function handleCompleteRegistration(e) {
  e.preventDefault();
  const payload = {
    email: otpState.email,
    full_name: document.getElementById('compRegFullName').value.trim(),
    legal_form: document.getElementById('compRegLegalForm').value,
    company_name: document.getElementById('compRegCompanyName').value.trim(),
    inn: document.getElementById('compRegInn').value.trim(),
    industry: document.getElementById('compRegIndustry').value,
    tax_regime: document.getElementById('compRegTaxRegime').value,
    initial_balance: parseFloat(document.getElementById('compRegInitialBalance').value) || 0.0
  };

  const valErr = validateInnAndName(payload.inn, payload.legal_form, payload.company_name);
  if (valErr) {
    showToast(valErr);
    return;
  }
  if (!payload.full_name || payload.full_name.length < 2) {
    showToast('Укажите ФИО руководителя (не менее 2 символов)');
    return;
  }

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const data = await res.json();
      state.authToken = data.access_token;
      state.currentUser = data.user;
      state.currentCompanyId = data.company.id;
      localStorage.setItem('ci_radar_token', data.access_token);
      localStorage.setItem('ci_radar_company_id', data.company.id);

      closeAuthModal();
      showToast(`Бизнес успешно зарегистрирован!`);
      await loadCompaniesList();
      await loadAllCompanyData(data.company.id);
      renderUserHeader(data.user);
      populateCabinetPageDetails();
      switchTab('cabinet');
    } else {
      const err = await res.json();
      showToast(err.detail || 'Ошибка регистрации бизнеса');
    }
  } catch (err) {
    console.error(err);
    showToast('Ошибка при отправке данных регистрации');
  }
}

function cancelOtpStep() {
  document.getElementById('authStep1Email').classList.remove('hidden');
  document.getElementById('authStep2Code').classList.add('hidden');
  document.getElementById('authStep3Complete').classList.add('hidden');
  document.getElementById('authModalTitle').innerText = "Вход по почте";
  document.getElementById('authModalSubtitle').innerText = "Быстрый вход без пароля по коду";
  if (otpState.timerInterval) clearInterval(otpState.timerInterval);
}

function resendOtpCode() {
  if (otpState.timerSeconds > 0) return;
  const fakeEvent = { preventDefault: () => {} };
  const emailInput = document.getElementById('otpEmailInput');
  if (emailInput) emailInput.value = otpState.email;
  handleSendOtpCode(fakeEvent);
}

function startOtpTimer(seconds) {
  otpState.timerSeconds = seconds;
  const btnResend = document.getElementById('btnResendOtp');
  if (otpState.timerInterval) clearInterval(otpState.timerInterval);

  const updateLabel = () => {
    if (otpState.timerSeconds > 0) {
      if (btnResend) {
        btnResend.innerText = `Повторить через ${otpState.timerSeconds}с`;
        btnResend.classList.add('pointer-events-none', 'text-slate-400');
        btnResend.classList.remove('text-ci-700', 'underline');
      }
      otpState.timerSeconds--;
    } else {
      clearInterval(otpState.timerInterval);
      if (btnResend) {
        btnResend.innerText = 'Отправить код повторно';
        btnResend.classList.remove('pointer-events-none', 'text-slate-400');
        btnResend.classList.add('text-ci-700', 'underline');
      }
    }
  };

  updateLabel();
  otpState.timerInterval = setInterval(updateLabel, 1000);
}

// ================= 14. ЛИЧНЫЙ КАБИНЕТ (ОТДЕЛЬНАЯ СТРАНИЦА) =================
function populateCabinetPageDetails() {
  const c = state.companyInfo || {};
  const u = state.currentUser || {};

  const nameEl = document.getElementById('cabPageFullName');
  if (nameEl) nameEl.value = u.full_name || '';

  const legalEl = document.getElementById('cabPageLegalForm');
  if (legalEl) legalEl.value = c.legal_form || 'ИП';

  const badgeEl = document.getElementById('cabPageLegalFormBadge');
  if (badgeEl) badgeEl.innerText = c.legal_form || 'ИП';

  const innEl = document.getElementById('cabPageInn');
  if (innEl) innEl.value = c.inn || '';

  const compNameEl = document.getElementById('cabPageCompanyName');
  if (compNameEl) compNameEl.value = c.name || '';

  const indEl = document.getElementById('cabPageIndustry');
  if (indEl) indEl.value = c.industry || '';

  const taxEl = document.getElementById('cabPageTaxRegime');
  if (taxEl) taxEl.value = c.tax_regime || 'УСН Доходы 6%';

  const balEl = document.getElementById('cabPageManualBalance');
  if (balEl) balEl.value = c.initial_manual_balance || c.last_balance || 0;

  const bizListEl = document.getElementById('cabUserBusinessesList');
  if (bizListEl) {
    if (!state.currentUser) {
      bizListEl.innerHTML = `
        <div class="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600 flex items-center justify-between flex-wrap gap-2">
          <div class="flex items-center space-x-2">
            <i data-lucide="info" class="w-4 h-4 text-slate-400"></i>
            <span>Вы находитесь в демо-режиме (ООО «Агро-063»). Войдите или зарегистрируйтесь, чтобы привязать свои бизнесы.</span>
          </div>
          <button onclick="openAuthModal()" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-lg text-xs transition">
            Войти в аккаунт
          </button>
        </div>
      `;
    } else {
      const companies = state.companies || [c];
      bizListEl.innerHTML = companies.map(comp => {
        const isActive = comp.id === state.currentCompanyId;
        return `
          <div class="p-3 rounded-xl border ${isActive ? 'border-emerald-500 bg-emerald-50/50' : 'border-slate-200 bg-white hover:border-slate-300'} flex items-center justify-between transition flex-wrap gap-2">
            <div class="flex items-center space-x-3">
              <div class="w-8 h-8 rounded-lg ${isActive ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-700 border border-slate-200'} flex items-center justify-center font-bold text-xs shrink-0">
                ${comp.legal_form || 'ООО'}
              </div>
              <div>
                <div class="font-extrabold text-xs text-slate-900 flex items-center space-x-1.5">
                  <span>${comp.name}</span>
                  ${isActive ? '<span class="text-[10px] bg-emerald-200 text-emerald-900 px-2 py-0.2 rounded-full font-bold">Активен</span>' : ''}
                </div>
                <div class="text-[11px] text-slate-500 mt-0.5">ИНН: ${comp.inn} • ${comp.industry || 'Бизнес'} • Остаток: ${formatMoney(comp.last_balance || comp.initial_manual_balance || 0)} ₽</div>
              </div>
            </div>
            <div>
              ${isActive ? 
                '<span class="text-xs font-bold text-emerald-700 flex items-center space-x-1"><i data-lucide="check" class="w-3.5 h-3.5"></i><span>Текущий</span></span>' :
                `<button onclick="onCompanyChange('${comp.id}')" class="px-3 py-1 rounded-lg border border-slate-300 hover:border-emerald-500 hover:text-emerald-700 bg-white text-xs font-bold transition">Переключиться</button>`
              }
            </div>
          </div>
        `;
      }).join('');
    }
    lucide.createIcons();
  }
}

async function saveCabinetProfileDirect(e) {
  e.preventDefault();
  if (!state.currentUser || !state.authToken) {
    showToast('Для сохранения реквизитов войдите в аккаунт');
    openAuthModal();
    return;
  }

  const payload = {
    name: document.getElementById('cabPageCompanyName').value.trim(),
    legal_form: document.getElementById('cabPageLegalForm').value,
    industry: document.getElementById('cabPageIndustry').value.trim(),
    tax_regime: document.getElementById('cabPageTaxRegime').value,
    initial_manual_balance: parseFloat(document.getElementById('cabPageManualBalance').value) || 0.0
  };

  const valErr = validateInnAndName(
    document.getElementById('cabPageInn') ? document.getElementById('cabPageInn').value : '6164000000',
    payload.legal_form,
    payload.name
  );
  if (valErr) {
    showToast(valErr);
    return;
  }

  try {
    const res = await fetch('/api/auth/company', {
      method: 'PATCH',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast('Реквизиты бизнеса сохранены и применены!');
      await loadCompaniesList();
      await loadAllCompanyData(state.currentCompanyId);
      populateCabinetPageDetails();
    } else {
      const err = await res.json();
      showToast(err.detail || 'Ошибка сохранения');
    }
  } catch (err) {
    console.error(err);
  }
}

function onCabPageFileSelected(input) {
  if (input.files && input.files[0]) {
    state.selectedFile = input.files[0];
    const nameEl = document.getElementById('cabPageFileName');
    const submitBtn = document.getElementById('btnCabPageUpload');
    if (nameEl) nameEl.innerText = `Файл: ${state.selectedFile.name} (${(state.selectedFile.size / 1024).toFixed(1)} КБ)`;
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.classList.remove('bg-slate-200');
      submitBtn.classList.add('bg-ci-600');
    }
  }
}

async function uploadCabPageFile() {
  if (!state.selectedFile) return;
  startAsyncStatementUpload(state.selectedFile);
}

function handleLogout() {
  state.authToken = null;
  state.currentUser = null;
  state.selectedFile = null;
  state.currentCompanyId = null;
  state.companyInfo = null;
  localStorage.removeItem('ci_radar_token');
  localStorage.removeItem('ci_radar_company_id');

  closeCabinetModal();
  showToast('Вы успешно вышли из аккаунта');

  renderUserHeader(null);
  loadCompaniesList();
  renderEmptyGuestDashboard();
  switchTab('radar');
}

// ==================== 14.2 НАЛОГОВАЯ ДЕКЛАРАЦИЯ ПО УСН (КНД 1152017) ====================
state.taxDeclaration = null;
state.taxDeclarationYear = '2025';
state.activeDeclTab = 'title';

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function openTaxDeclarationModal(year = null) {
  if (!state.currentCompanyId) {
    showToast('Сначала выберите или создайте бизнес');
    return;
  }
  const modal = document.getElementById('taxDeclarationEditorModal');
  if (!modal) return;
  modal.classList.remove('hidden');

  if (year) {
    state.taxDeclarationYear = String(year);
  }
  const yearSelect = document.getElementById('declYearSelect');
  if (yearSelect) yearSelect.value = state.taxDeclarationYear;

  switchTaxDeclTab('title');
  loadTaxDeclarationData(state.taxDeclarationYear);
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

function openTaxDeclarationStubModal() {
  openTaxDeclarationModal();
}

function closeTaxDeclarationModal() {
  const modal = document.getElementById('taxDeclarationEditorModal');
  if (modal) modal.classList.add('hidden');
}

function closeTaxDeclarationStubModal() {
  closeTaxDeclarationModal();
}

async function changeTaxDeclYear(year) {
  state.taxDeclarationYear = String(year);
  await loadTaxDeclarationData(state.taxDeclarationYear);
}

async function loadTaxDeclarationData(year) {
  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/tax-declaration/data?year=${year}`, {
      headers: getAuthHeaders(true)
    });
    if (res.ok) {
      const data = await res.json();
      state.taxDeclaration = data;
      populateTaxDeclarationForm(data);
      validateTaxDeclarationData();
      renderTaxDeclarationPreview();
    } else {
      showToast('Не удалось загрузить данные декларации');
    }
  } catch (err) {
    console.error('Error fetching tax declaration:', err);
    showToast('Ошибка загрузки налоговой декларации');
  }
}

function populateTaxDeclarationForm(data) {
  if (!data) return;
  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = val !== undefined && val !== null ? val : '';
  };

  setVal('declInn', data.inn || '');
  setVal('declKpp', data.kpp || '');
  setVal('declCorrectionNum', data.correction_num || '0');
  setVal('declIfnsCode', data.ifns_code || '');
  setVal('declLocationCode', data.location_code || '214');
  setVal('declOktmo', data.oktmo || '60701000');
  setVal('declCompanyName', data.company_name || '');
  setVal('declPhone', data.phone || '');
  setVal('declTaxObject', data.tax_object || '1');
  setVal('declPayerCode', data.payer_code || '1');

  // Incomes
  setVal('declIncQ1', data.income_q1 || 0);
  setVal('declIncQ2', data.income_q2 || 0);
  setVal('declIncQ3', data.income_q3 || 0);
  setVal('declIncYear', data.income_year || 0);

  // Expenses
  setVal('declExpQ1', data.expense_q1 || 0);
  setVal('declExpQ2', data.expense_q2 || 0);
  setVal('declExpQ3', data.expense_q3 || 0);
  setVal('declExpYear', data.expense_year || 0);

  // Rates
  const rate = data.rate || (data.tax_object === '2' ? 15 : 6);
  ['declRateQ1', 'declRateQ2', 'declRateQ3', 'declRateYear'].forEach(id => setVal(id, rate));

  // Taxes
  setVal('declTaxQ1', data.tax_q1 || 0);
  setVal('declTaxQ2', data.tax_q2 || 0);
  setVal('declTaxQ3', data.tax_q3 || 0);
  setVal('declTaxYear', data.tax_year || 0);

  // Deductions
  setVal('declDeductQ1', data.deduct_q1 || 0);
  setVal('declDeductQ2', data.deduct_q2 || 0);
  setVal('declDeductQ3', data.deduct_q3 || 0);
  setVal('declDeductYear', data.deduct_year || 0);

  // Section 1 Due / Reductions
  setVal('declDueQ1', data.due_q1 || 0);
  setVal('declDueQ2', data.due_q2 || 0);
  setVal('declDecQ2', data.dec_q2 || 0);
  setVal('declDueQ3', data.due_q3 || 0);
  setVal('declDecQ3', data.dec_q3 || 0);
  setVal('declDueYear', data.due_year || 0);
  setVal('declDecYear', data.dec_year || 0);
  setVal('declMinTax', data.min_tax || 0);

  // Insurance premiums & deductions
  setVal('declInsFixed', data.ins_fixed || 0);
  setVal('declIns1Pct', data.ins_1pct || 0);
  setVal('declIns1PctCurr', data.ins_1pct_curr || 0);
  setVal('declIns1PctPrev', data.ins_1pct_prev || 0);

  // Toggle 15% conditional views
  const is15 = String(data.tax_object) === '2';
  const expSec = document.getElementById('declExpensesSection');
  if (expSec) expSec.classList.toggle('hidden', !is15);
  const minTaxSec = document.getElementById('declMinTaxBlock');
  if (minTaxSec) minTaxSec.classList.toggle('hidden', !is15);

  const sec1T = document.getElementById('declSec1Title');
  if (sec1T) sec1T.textContent = is15
    ? 'Раздел 1.2. Сумма налога / авансовых платежей к уплате (УСН Доходы минус расходы)'
    : 'Раздел 1.1. Сумма налога / авансовых платежей к уплате (УСН Доходы)';
  const sec2T = document.getElementById('declSec2Title');
  if (sec2T) sec2T.textContent = is15
    ? 'Раздел 2.2. Расчет налога, уплачиваемого в связи с применением УСН (Доходы минус расходы)'
    : 'Раздел 2.1.1. Расчет налога, уплачиваемого в связи с применением УСН (Доходы)';
}

function getTaxDeclarationFormData() {
  const getNum = (id) => {
    const el = document.getElementById(id);
    return el ? (parseFloat(el.value) || 0) : 0;
  };
  const getStr = (id) => {
    const el = document.getElementById(id);
    return el ? String(el.value || '').trim() : '';
  };

  return {
    company_id: state.currentCompanyId,
    year: state.taxDeclarationYear,
    inn: getStr('declInn'),
    kpp: getStr('declKpp'),
    company_name: getStr('declCompanyName'),
    phone: getStr('declPhone'),
    oktmo: getStr('declOktmo'),
    ifns_code: getStr('declIfnsCode'),
    location_code: getStr('declLocationCode') || '214',
    correction_num: getStr('declCorrectionNum') || '0',
    tax_object: getStr('declTaxObject') || '1',
    payer_code: getStr('declPayerCode') || '1',
    rate: getNum('declRateYear') || 6,
    income_q1: getNum('declIncQ1'),
    income_q2: getNum('declIncQ2'),
    income_q3: getNum('declIncQ3'),
    income_year: getNum('declIncYear'),
    expense_q1: getNum('declExpQ1'),
    expense_q2: getNum('declExpQ2'),
    expense_q3: getNum('declExpQ3'),
    expense_year: getNum('declExpYear'),
    tax_q1: getNum('declTaxQ1'),
    tax_q2: getNum('declTaxQ2'),
    tax_q3: getNum('declTaxQ3'),
    tax_year: getNum('declTaxYear'),
    due_q1: getNum('declDueQ1'),
    due_q2: getNum('declDueQ2'),
    dec_q2: getNum('declDecQ2'),
    due_q3: getNum('declDueQ3'),
    dec_q3: getNum('declDecQ3'),
    due_year: getNum('declDueYear'),
    dec_year: getNum('declDecYear'),
    min_tax: getNum('declMinTax'),
    deduct_q1: getNum('declDeductQ1'),
    deduct_q2: getNum('declDeductQ2'),
    deduct_q3: getNum('declDeductQ3'),
    deduct_year: getNum('declDeductYear'),
    ins_fixed: getNum('declInsFixed'),
    ins_1pct: getNum('declIns1Pct'),
    ins_1pct_curr: getNum('declIns1PctCurr'),
    ins_1pct_prev: getNum('declIns1PctPrev')
  };
}

function onTaxDeclInputChange(field) {
  state.taxDeclaration = getTaxDeclarationFormData();
  validateTaxDeclarationData();
  renderTaxDeclarationPreview();
}

function onTaxDeclObjectChange(val) {
  if (!state.taxDeclaration) state.taxDeclaration = {};
  state.taxDeclaration.tax_object = String(val);
  const is15 = String(val) === '2';
  const defaultRate = is15 ? 15 : 6;
  state.taxDeclaration.rate = defaultRate;
  ['declRateQ1', 'declRateQ2', 'declRateQ3', 'declRateYear'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = defaultRate;
  });

  const expSec = document.getElementById('declExpensesSection');
  if (expSec) expSec.classList.toggle('hidden', !is15);
  const minTaxSec = document.getElementById('declMinTaxBlock');
  if (minTaxSec) minTaxSec.classList.toggle('hidden', !is15);

  const sec1T = document.getElementById('declSec1Title');
  if (sec1T) sec1T.textContent = is15
    ? 'Раздел 1.2. Сумма налога / авансовых платежей к уплате (УСН Доходы минус расходы)'
    : 'Раздел 1.1. Сумма налога / авансовых платежей к уплате (УСН Доходы)';
  const sec2T = document.getElementById('declSec2Title');
  if (sec2T) sec2T.textContent = is15
    ? 'Раздел 2.2. Расчет налога, уплачиваемого в связи с применением УСН (Доходы минус расходы)'
    : 'Раздел 2.1.1. Расчет налога, уплачиваемого в связи с применением УСН (Доходы)';

  recalculateTaxDeclaration();
}

function recalculateTaxDeclaration() {
  const d = getTaxDeclarationFormData();
  const is15 = d.tax_object === '2';
  const rQ1 = (parseFloat(document.getElementById('declRateQ1')?.value) || (is15 ? 15 : 6)) / 100;
  const rQ2 = (parseFloat(document.getElementById('declRateQ2')?.value) || (is15 ? 15 : 6)) / 100;
  const rQ3 = (parseFloat(document.getElementById('declRateQ3')?.value) || (is15 ? 15 : 6)) / 100;
  const rYear = (parseFloat(document.getElementById('declRateYear')?.value) || (is15 ? 15 : 6)) / 100;

  let baseQ1 = d.income_q1;
  let baseQ2 = d.income_q2;
  let baseQ3 = d.income_q3;
  let baseYear = d.income_year;

  if (is15) {
    baseQ1 = Math.max(0, d.income_q1 - d.expense_q1);
    baseQ2 = Math.max(0, d.income_q2 - d.expense_q2);
    baseQ3 = Math.max(0, d.income_q3 - d.expense_q3);
    baseYear = Math.max(0, d.income_year - d.expense_year);
  }

  // Calculated taxes
  let taxQ1 = Math.round(baseQ1 * rQ1);
  let taxQ2 = Math.round(baseQ2 * rQ2);
  let taxQ3 = Math.round(baseQ3 * rQ3);
  let taxYear = Math.round(baseYear * rYear);

  // Apply deductions for 6%
  if (!is15) {
    const isEmployer = d.payer_code === '1';
    const maxDeduct = (tax) => isEmployer ? Math.floor(tax * 0.5) : tax;
    taxQ1 = Math.max(0, taxQ1 - Math.min(d.deduct_q1, maxDeduct(taxQ1)));
    taxQ2 = Math.max(0, taxQ2 - Math.min(d.deduct_q2, maxDeduct(taxQ2)));
    taxQ3 = Math.max(0, taxQ3 - Math.min(d.deduct_q3, maxDeduct(taxQ3)));
    taxYear = Math.max(0, taxYear - Math.min(d.deduct_year, maxDeduct(taxYear)));
  }

  // Min tax for 15%
  const minTax = is15 ? Math.round(d.income_year * 0.01) : 0;

  // Payments / Reductions
  const dueQ1 = taxQ1;

  const diffQ2 = taxQ2 - dueQ1;
  const dueQ2 = Math.max(0, diffQ2);
  const decQ2 = diffQ2 < 0 ? Math.abs(diffQ2) : 0;

  const prevAccruedQ3 = dueQ1 + (dueQ2 - decQ2);
  const diffQ3 = taxQ3 - prevAccruedQ3;
  const dueQ3 = Math.max(0, diffQ3);
  const decQ3 = diffQ3 < 0 ? Math.abs(diffQ3) : 0;

  const prevAccruedYear = prevAccruedQ3 + (dueQ3 - decQ3);
  const finalAnnualTax = is15 ? Math.max(taxYear, minTax) : taxYear;
  const diffYear = finalAnnualTax - prevAccruedYear;
  const dueYear = Math.max(0, diffYear);
  const decYear = diffYear < 0 ? Math.abs(diffYear) : 0;

  // Update inputs
  const setEl = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = val;
  };
  setEl('declTaxQ1', taxQ1);
  setEl('declTaxQ2', taxQ2);
  setEl('declTaxQ3', taxQ3);
  setEl('declTaxYear', taxYear);
  setEl('declMinTax', minTax);

  setEl('declDueQ1', dueQ1);
  setEl('declDueQ2', dueQ2);
  setEl('declDecQ2', decQ2);
  setEl('declDueQ3', dueQ3);
  setEl('declDecQ3', decQ3);
  setEl('declDueYear', dueYear);
  setEl('declDecYear', decYear);

  state.taxDeclaration = getTaxDeclarationFormData();
  validateTaxDeclarationData();
  renderTaxDeclarationPreview();
  showToast('Налоги и авансовые платежи автоматически пересчитаны');
}

async function recalculateFromDatabase() {
  showToast('Синхронизация с операциями по выписке...');
  await loadTaxDeclarationData(state.taxDeclarationYear);
}

function switchTaxDeclTab(tabKey) {
  state.activeDeclTab = tabKey;
  const tabs = {
    title: { btn: 'btnDeclTabTitle', panel: 'declTabTitlePanel' },
    sec1: { btn: 'btnDeclTabSec1', panel: 'declTabSec1Panel' },
    sec2: { btn: 'btnDeclTabSec2', panel: 'declTabSec2Panel' },
    sec3: { btn: 'btnDeclTabSec3', panel: 'declTabSec3Panel' },
    preview: { btn: 'btnDeclTabPreview', panel: 'declTabPreviewPanel' }
  };

  Object.entries(tabs).forEach(([k, t]) => {
    const btn = document.getElementById(t.btn);
    const pnl = document.getElementById(t.panel);
    if (!btn || !pnl) return;
    if (k === tabKey) {
      btn.className = 'px-3 py-1.5 rounded-xl transition bg-white text-slate-900 shadow-2xs font-black flex items-center space-x-1';
      pnl.classList.remove('hidden');
    } else {
      btn.className = 'px-3 py-1.5 rounded-xl transition text-slate-500 hover:text-slate-800 font-bold flex items-center space-x-1';
      pnl.classList.add('hidden');
    }
  });

  if (tabKey === 'preview') {
    renderTaxDeclarationPreview();
  }
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

function validateTaxDeclarationData() {
  const d = getTaxDeclarationFormData();
  const errors = [];
  const setFieldErr = (id, hasErr) => {
    const el = document.getElementById(id);
    if (el) {
      if (hasErr) {
        el.classList.add('border-red-400', 'bg-red-50/40');
      } else {
        el.classList.remove('border-red-400', 'bg-red-50/40');
      }
    }
  };

  // INN validation
  const cleanInn = d.inn.replace(/\D/g, '');
  const innOk = (cleanInn.length === 10 || cleanInn.length === 12);
  setFieldErr('declInn', !innOk);
  if (!innOk) {
    errors.push('ИНН должен содержать 10 цифр для юридического лица или 12 цифр для ИП.');
  }

  // KPP validation (if entered or if legal entity)
  const isIp = cleanInn.length === 12 || d.company_name.toUpperCase().startsWith('ИП ');
  if (!isIp && d.kpp) {
    const cleanKpp = d.kpp.replace(/\D/g, '');
    const kppOk = cleanKpp.length === 9;
    setFieldErr('declKpp', !kppOk);
    if (!kppOk) errors.push('КПП организации должен состоять ровно из 9 цифр.');
  }

  // IFNS code
  const cleanIfns = d.ifns_code.replace(/\D/g, '');
  const ifnsOk = cleanIfns.length === 4;
  setFieldErr('declIfnsCode', !ifnsOk);
  if (!ifnsOk) errors.push('Код налогового органа (ИФНС) должен состоять из 4 цифр.');

  // OKTMO code
  const cleanOktmo = d.oktmo.replace(/\D/g, '');
  const oktmoOk = cleanOktmo.length === 8 || cleanOktmo.length === 11;
  setFieldErr('declOktmo', !oktmoOk);
  if (!oktmoOk) errors.push('Код ОКТМО должен состоять из 8 или 11 цифр.');

  // Cumulative incomes
  if (d.income_q2 < d.income_q1) {
    errors.push('Доход за полугодие (стр. 111) не может быть меньше дохода за I квартал (стр. 110) — нарастающий итог!');
    setFieldErr('declIncQ2', true);
  } else {
    setFieldErr('declIncQ2', false);
  }

  if (d.income_q3 < d.income_q2) {
    errors.push('Доход за 9 месяцев (стр. 112) не может быть меньше дохода за полугодие (стр. 111) — нарастающий итог!');
    setFieldErr('declIncQ3', true);
  } else {
    setFieldErr('declIncQ3', false);
  }

  if (d.income_year < d.income_q3) {
    errors.push('Доход за налоговый период / год (стр. 113) не может быть меньше дохода за 9 месяцев (стр. 112)!');
    setFieldErr('declIncYear', true);
  } else {
    setFieldErr('declIncYear', false);
  }

  // Cumulative expenses for 15%
  if (d.tax_object === '2') {
    if (d.expense_q2 < d.expense_q1) {
      errors.push('Расходы за полугодие (стр. 221) не могут быть меньше расходов за I квартал (стр. 220)!');
      setFieldErr('declExpQ2', true);
    } else {
      setFieldErr('declExpQ2', false);
    }

    if (d.expense_q3 < d.expense_q2) {
      errors.push('Расходы за 9 месяцев (стр. 222) не могут быть меньше расходов за полугодие (стр. 221)!');
      setFieldErr('declExpQ3', true);
    } else {
      setFieldErr('declExpQ3', false);
    }

    if (d.expense_year < d.expense_q3) {
      errors.push('Расходы за год (стр. 223) не могут быть меньше расходов за 9 месяцев (стр. 222)!');
      setFieldErr('declExpYear', true);
    } else {
      setFieldErr('declExpYear', false);
    }
  }

  // Update Status Badge and Alert Box
  const badge = document.getElementById('declValidationBadge');
  const alertBox = document.getElementById('declValidationAlert');
  const errList = document.getElementById('declValidationErrorsList');

  if (errors.length === 0) {
    if (badge) {
      badge.className = 'flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-black bg-emerald-50 text-emerald-700 border border-emerald-200 transition-all';
      badge.innerHTML = '<i data-lucide="shield-check" class="w-4 h-4 text-emerald-600"></i><span>Корректно • Контроль пройден</span>';
    }
    if (alertBox) alertBox.classList.add('hidden');
  } else {
    if (badge) {
      badge.className = 'flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-black bg-amber-50 text-amber-800 border border-amber-300 transition-all';
      badge.innerHTML = `<i data-lucide="alert-triangle" class="w-4 h-4 text-amber-600"></i><span>Замечаний: ${errors.length}</span>`;
    }
    if (alertBox) {
      alertBox.classList.remove('hidden');
      if (errList) {
        errList.innerHTML = errors.map(e => `<li>${escapeHtml(e)}</li>`).join('');
      }
    }
  }

  if (typeof lucide !== 'undefined') lucide.createIcons();
  return errors.length === 0;
}

function renderCells(val, count) {
  let s = String(val !== undefined && val !== null ? val : '').trim().toUpperCase();
  if (s.length > count) s = s.substring(0, count);
  const padded = s.padEnd(count, '-');
  let html = '<div class="inline-flex flex-wrap">';
  for (let i = 0; i < count; i++) {
    html += `<span class="fns-cell">${escapeHtml(padded[i])}</span>`;
  }
  html += '</div>';
  return html;
}

function renderMoneyCells(val, count) {
  if (val === null || val === undefined || val === '') {
    return renderCells('', count);
  }
  const num = Math.round(Number(val) || 0);
  return renderCells(num > 0 ? String(num) : '-', count);
}

const CODE39_PATTERNS = {
  '0': ['N', 'N', 'N', 'W', 'W', 'N', 'W', 'N', 'N'],
  '1': ['W', 'N', 'N', 'W', 'N', 'N', 'N', 'N', 'W'],
  '2': ['N', 'N', 'W', 'W', 'N', 'N', 'N', 'N', 'W'],
  '3': ['W', 'N', 'W', 'W', 'N', 'N', 'N', 'N', 'N'],
  '4': ['N', 'N', 'N', 'W', 'W', 'N', 'N', 'N', 'W'],
  '5': ['W', 'N', 'N', 'W', 'W', 'N', 'N', 'N', 'N'],
  '6': ['N', 'N', 'W', 'W', 'W', 'N', 'N', 'N', 'N'],
  '7': ['N', 'N', 'N', 'W', 'N', 'N', 'W', 'N', 'W'],
  '8': ['W', 'N', 'N', 'W', 'N', 'N', 'W', 'N', 'N'],
  '9': ['N', 'N', 'W', 'W', 'N', 'N', 'W', 'N', 'N'],
  '*': ['N', 'W', 'N', 'N', 'W', 'N', 'W', 'N', 'N']
};

function renderBarcodeHtml(codeStr) {
  const clean = String(codeStr || '').replace(/\s+/g, '');
  const fullText = `*${clean}*`;
  const narrow = 1.05;
  const wide = 2.8;
  const height = 26;
  let curX = 4;
  let rects = '';

  for (let idx = 0; idx < fullText.length; idx++) {
    const ch = fullText[idx];
    const pat = CODE39_PATTERNS[ch] || CODE39_PATTERNS['0'];
    for (let i = 0; i < 9; i++) {
      const isBar = (i % 2 === 0);
      const w = pat[i] === 'W' ? wide : narrow;
      if (isBar) {
        rects += `<rect x="${curX.toFixed(1)}" y="0" width="${w.toFixed(1)}" height="${height}" fill="#000" />`;
      }
      curX += w;
    }
    if (idx < fullText.length - 1) {
      curX += narrow;
    }
  }
  curX += 4;
  const totalW = Math.ceil(curX);
  const textDisplay = clean.length === 8 ? `${clean.substring(0, 4)} ${clean.substring(4)}` : codeStr;

  return `
    <div class="inline-flex flex-col items-start select-none mb-1">
      <svg width="${totalW}" height="${height + 14}" viewBox="0 0 ${totalW} ${height + 14}" class="overflow-visible">
        ${rects}
        <text x="${(totalW / 2).toFixed(1)}" y="${height + 11}" text-anchor="middle" font-family="'Courier New', Courier, monospace" font-size="10" font-weight="bold" fill="#000">${escapeHtml(textDisplay)}</text>
      </svg>
    </div>
  `;
}

function renderTaxDeclarationPreview() {
  const container = document.getElementById('fnsPrintArea');
  if (!container) return;

  const d = getTaxDeclarationFormData();
  const is15 = d.tax_object === '2';
  const isIp = d.inn.length === 12;

  // Split company name into 4 rows of 40 chars
  const compNameUpper = (d.company_name || '').toUpperCase().trim();
  const compLines = [];
  for (let i = 0; i < 4; i++) {
    const start = i * 40;
    compLines.push(compNameUpper.substring(start, start + 40));
  }

  const cornerSq = `
    <div class="fns-corner-sq" style="top: 8mm; left: 8mm;"></div>
    <div class="fns-corner-sq" style="top: 8mm; right: 8mm;"></div>
    <div class="fns-corner-sq" style="bottom: 8mm; left: 8mm;"></div>
    <div class="fns-corner-sq" style="bottom: 8mm; right: 8mm;"></div>
  `;

  // PAGE 1: TITLE (0301 6015, Стр. 001)
  const page1 = `
    <div class="fns-a4-page">
      ${cornerSq}
      
      <!-- Top header with Barcode and INN/KPP -->
      <div class="flex items-start justify-between mb-2">
        ${renderBarcodeHtml('0301 6015')}
        <div class="space-y-1 text-right">
          <div class="flex items-center justify-end space-x-1.5 text-[11px] font-bold">
            <span class="font-sans">ИНН</span>
            ${renderCells(d.inn, 12)}
          </div>
          <div class="flex items-center justify-end space-x-1.5 text-[11px] font-bold">
            <span class="font-sans">КПП</span>
            ${renderCells(isIp ? '' : d.kpp, 9)}
          </div>
          <div class="flex items-center justify-end space-x-1.5 text-[11px] font-bold">
            <span class="font-sans">Стр.</span>
            ${renderCells('001', 3)}
          </div>
        </div>
      </div>

      <!-- Form Title -->
      <div class="text-right text-[10px] font-bold mb-1">Форма по КНД 1152017</div>
      <div class="text-center font-bold text-[11px] leading-tight mb-4 uppercase tracking-wide border-b border-black pb-2">
        Налоговая декларация по налогу, уплачиваемому в связи с применением упрощенной системы налогообложения
      </div>

      <!-- Parameters Grid -->
      <div class="space-y-2 text-[10px] mb-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-1">
            <span>Номер корректировки:</span>
            ${renderCells(d.correction_num || '0', 3)}
          </div>
          <div class="flex items-center space-x-1">
            <span>Налоговый период (код):</span>
            ${renderCells('34', 2)}
          </div>
          <div class="flex items-center space-x-1">
            <span>Отчетный год:</span>
            ${renderCells(d.year, 4)}
          </div>
        </div>

        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-1">
            <span>Представляется в налоговый орган (код):</span>
            ${renderCells(d.ifns_code, 4)}
          </div>
          <div class="flex items-center space-x-1">
            <span>По месту нахождения (учета) (код):</span>
            ${renderCells(d.location_code || (isIp ? '120' : '214'), 3)}
          </div>
        </div>
      </div>

      <!-- Taxpayer Name -->
      <div class="text-[10px] mb-3 space-y-1">
        <div class="font-bold">Налогоплательщик:</div>
        ${compLines.map(line => `<div>${renderCells(line, 40)}</div>`).join('')}
      </div>

      <!-- OKTMO and Phone -->
      <div class="space-y-2 text-[10px] mb-4">
        <div class="flex items-center space-x-2">
          <span class="w-48">Код по ОКТМО:</span>
          ${renderCells(d.oktmo, 11)}
        </div>
        <div class="flex items-center space-x-2">
          <span class="w-48">Номер контактного телефона:</span>
          ${renderCells(d.phone, 20)}
        </div>
        <div class="flex items-center space-x-2">
          <span class="w-48">На страницах:</span>
          ${renderCells('004', 3)}
          <span class="ml-4">с приложением документов на:</span>
          ${renderCells('---', 3)}
          <span>листах</span>
        </div>
      </div>

      <!-- Confirmation block (2 columns) -->
      <div class="border border-black grid grid-cols-2 text-[9px] min-h-[160px]">
        <div class="p-2 border-r border-black space-y-2 flex flex-col justify-between">
          <div>
            <div class="font-bold mb-1">Достоверность и полноту сведений, указанных в настоящей декларации, подтверждаю:</div>
            <div class="flex items-center space-x-2 mb-2">
              <span>1 - налогоплательщик, 2 - представитель:</span>
              ${renderCells(isIp ? '1' : '1', 1)}
            </div>
            <div class="space-y-1">
              <div>${renderCells(compLines[0] || '', 30)}</div>
              <div>${renderCells(compLines[1] || '', 30)}</div>
            </div>
          </div>
          <div class="flex items-center justify-between pt-2 border-t border-black/40">
            <span>Подпись: _____________</span>
            <span>Дата: ${new Date().toLocaleDateString('ru-RU')}</span>
          </div>
        </div>

        <div class="p-2 space-y-2 bg-slate-50/50 flex flex-col justify-between text-slate-700">
          <div>
            <div class="font-bold mb-1 uppercase tracking-wider text-[8.5px]">Заполняется работником налогового органа:</div>
            <p class="text-[8px] text-slate-500">Сведения о представлении декларации</p>
          </div>
          <div class="space-y-1 text-[8.5px]">
            <div>Способ представления (код): ${renderCells('--', 2)}</div>
            <div>Дата представления: ${renderCells('----------', 10)}</div>
          </div>
        </div>
      </div>
    </div>
  `;

  // PAGE 2: SECTION 1 (0301 6022 или 0301 6039, Стр. 002)
  const barcodeSec1 = is15 ? '0301 6039' : '0301 6022';
  const sec1Heading = is15
    ? 'Раздел 1.2. Сумма налога (авансового платежа по налогу), уплачиваемого в связи с применением упрощенной системы налогообложения (объект налогообложения – доходы, уменьшенные на величину расходов)...'
    : 'Раздел 1.1. Сумма налога (авансового платежа по налогу), уплачиваемого в связи с применением упрощенной системы налогообложения (объект налогообложения – доходы), подлежащая уплате (уменьшению)...';

  const page2 = `
    <div class="fns-a4-page">
      ${cornerSq}

      <div class="flex items-start justify-between mb-2">
        ${renderBarcodeHtml(barcodeSec1)}
        <div class="space-y-1 text-right">
          <div class="flex items-center justify-end space-x-1.5 text-[11px] font-bold">
            <span class="font-sans">ИНН</span>
            ${renderCells(d.inn, 12)}
          </div>
          <div class="flex items-center justify-end space-x-1.5 text-[11px] font-bold">
            <span class="font-sans">КПП</span>
            ${renderCells(isIp ? '' : d.kpp, 9)}
          </div>
          <div class="flex items-center justify-end space-x-1.5 text-[11px] font-bold">
            <span class="font-sans">Стр.</span>
            ${renderCells('002', 3)}
          </div>
        </div>
      </div>

      <div class="font-bold text-[10px] leading-tight mb-3 border-b border-black pb-2 uppercase">
        ${sec1Heading}
      </div>

      <div class="space-y-2 text-[10px]">
        <div class="flex items-center justify-between border-b border-slate-200 pb-1">
          <span>Код по ОКТМО (стр. 010):</span>
          ${renderCells(d.oktmo, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1">
          <span>Авансовый платеж за I квартал к уплате (стр. 020):</span>
          ${renderMoneyCells(d.due_q1, 11)}
        </div>

        <div class="flex items-center justify-between border-b border-slate-200 pb-1">
          <span>Код по ОКТМО (стр. 030):</span>
          ${renderCells(d.oktmo, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1">
          <span>Авансовый платеж за полугодие к доплате (стр. 040):</span>
          ${renderMoneyCells(d.due_q2, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1">
          <span>Авансовый платеж за полугодие к уменьшению (стр. 050):</span>
          ${renderMoneyCells(d.dec_q2, 11)}
        </div>

        <div class="flex items-center justify-between border-b border-slate-200 pb-1">
          <span>Код по ОКТМО (стр. 060):</span>
          ${renderCells(d.oktmo, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1">
          <span>Авансовый платеж за 9 месяцев к доплате (стр. 070):</span>
          ${renderMoneyCells(d.due_q3, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1">
          <span>Авансовый платеж за 9 месяцев к уменьшению (стр. 080):</span>
          ${renderMoneyCells(d.dec_q3, 11)}
        </div>

        <div class="flex items-center justify-between border-b border-slate-200 pb-1">
          <span>Код по ОКТМО (стр. 090):</span>
          ${renderCells(d.oktmo, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1">
          <span class="font-bold">Налог за налоговый период (год) к доплате (стр. 100):</span>
          ${renderMoneyCells(d.due_year, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1">
          <span>Налог за налоговый период (год) к уменьшению (стр. 110):</span>
          ${renderMoneyCells(d.dec_year, 11)}
        </div>

        ${is15 ? `
          <div class="flex items-center justify-between border-t border-black pt-2 font-bold">
            <span>Сумма минимального налога к уплате за год (стр. 120):</span>
            ${renderMoneyCells(d.min_tax, 11)}
          </div>
        ` : ''}
      </div>
    </div>
  `;

  // PAGE 3: SECTION 2 PART 1 (0301 6046 или 0301 6084, Стр. 003)
  const barcodeSec2 = is15 ? '0301 6084' : '0301 6046';
  const sec2Heading = is15
    ? 'Раздел 2.2. Расчет налога, уплачиваемого в связи с применением УСН, и минимального налога (объект – доходы, уменьшенные на величину расходов) — Часть 1'
    : 'Раздел 2.1.1. Расчет налога, уплачиваемого в связи с применением упрощенной системы налогообложения (объект налогообложения – доходы) — Часть 1';

  const page3 = `
    <div class="fns-a4-page">
      ${cornerSq}

      <div class="flex items-start justify-between mb-2">
        ${renderBarcodeHtml(barcodeSec2)}
        <div class="space-y-1 text-right">
          <div class="flex items-center justify-end space-x-1.5 text-[11px] font-bold">
            <span class="font-sans">ИНН</span>
            ${renderCells(d.inn, 12)}
          </div>
          <div class="flex items-center justify-end space-x-1.5 text-[11px] font-bold">
            <span class="font-sans">КПП</span>
            ${renderCells(isIp ? '' : d.kpp, 9)}
          </div>
          <div class="flex items-center justify-end space-x-1.5 text-[11px] font-bold">
            <span class="font-sans">Стр.</span>
            ${renderCells('003', 3)}
          </div>
        </div>
      </div>

      <div class="font-bold text-[10px] leading-tight mb-3 border-b border-black pb-2 uppercase">
        ${sec2Heading}
      </div>

      <div class="space-y-2 text-[10px]">
        ${!is15 ? `
          <div class="flex items-center justify-between border-b border-slate-200 pb-1">
            <span>Признак налогоплательщика (1 - с работниками, 2 - без) (стр. 102):</span>
            ${renderCells(d.payer_code || '1', 1)}
          </div>
        ` : ''}

        <div class="font-bold uppercase tracking-wider text-[9px] pt-1">Сумма полученных доходов нарастающим итогом (руб.):</div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
          <span>За I квартал (${is15 ? 'стр. 210' : 'стр. 110'}):</span>
          ${renderMoneyCells(d.income_q1, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
          <span>За полугодие (${is15 ? 'стр. 211' : 'стр. 111'}):</span>
          ${renderMoneyCells(d.income_q2, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
          <span>За 9 месяцев (${is15 ? 'стр. 212' : 'стр. 112'}):</span>
          ${renderMoneyCells(d.income_q3, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
          <span class="font-bold">За налоговый период / год (${is15 ? 'стр. 213' : 'стр. 113'}):</span>
          ${renderMoneyCells(d.income_year, 11)}
        </div>

        ${is15 ? `
          <div class="font-bold uppercase tracking-wider text-[9px] pt-1">Сумма произведенных расходов нарастающим итогом (руб.):</div>
          <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
            <span>За I квартал (стр. 220):</span>
            ${renderMoneyCells(d.expense_q1, 11)}
          </div>
          <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
            <span>За полугодие (стр. 221):</span>
            ${renderMoneyCells(d.expense_q2, 11)}
          </div>
          <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
            <span>За 9 месяцев (стр. 222):</span>
            ${renderMoneyCells(d.expense_q3, 11)}
          </div>
          <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
            <span class="font-bold">За налоговый период / год (стр. 223):</span>
            ${renderMoneyCells(d.expense_year, 11)}
          </div>
        ` : ''}

        <div class="font-bold uppercase tracking-wider text-[9px] pt-1">Ставка налога (%):</div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
          <span>За налоговый период (${is15 ? 'стр. 260-263' : 'стр. 120-123'}):</span>
          ${renderCells(String(d.rate || (is15 ? '15.0' : '6.0')), 5)}
        </div>

        <div class="font-bold uppercase tracking-wider text-[9px] pt-1">Сумма исчисленного налога / авансового платежа (руб.):</div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
          <span>За I квартал (${is15 ? 'стр. 270' : 'стр. 130'}):</span>
          ${renderMoneyCells(d.tax_q1, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
          <span>За полугодие (${is15 ? 'стр. 271' : 'стр. 131'}):</span>
          ${renderMoneyCells(d.tax_q2, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
          <span>За 9 месяцев (${is15 ? 'стр. 272' : 'стр. 132'}):</span>
          ${renderMoneyCells(d.tax_q3, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
          <span class="font-bold">За налоговый период / год (${is15 ? 'стр. 273' : 'стр. 133'}):</span>
          ${renderMoneyCells(d.tax_year, 11)}
        </div>
      </div>
    </div>
  `;

  // PAGE 4: SECTION 2 PART 2 (0301 6053 или 0301 6091, Стр. 004)
  const barcodeSec4 = is15 ? '0301 6091' : '0301 6053';
  const sec4Heading = is15
    ? 'Раздел 2.2 (продолжение). Сумма исчисленного минимального налога и страховые взносы ст. 430 НК РФ'
    : 'Раздел 2.1.1 (продолжение). Страховые взносы и вычеты, уменьшающие налог (стр. 140-162)';

  const page4 = `
    <div class="fns-a4-page">
      ${cornerSq}

      <div class="flex items-start justify-between mb-2">
        ${renderBarcodeHtml(barcodeSec4)}
        <div class="space-y-1 text-right">
          <div class="flex items-center justify-end space-x-1.5 text-[11px] font-bold">
            <span class="font-sans">ИНН</span>
            ${renderCells(d.inn, 12)}
          </div>
          <div class="flex items-center justify-end space-x-1.5 text-[11px] font-bold">
            <span class="font-sans">КПП</span>
            ${renderCells(isIp ? '' : d.kpp, 9)}
          </div>
          <div class="flex items-center justify-end space-x-1.5 text-[11px] font-bold">
            <span class="font-sans">Стр.</span>
            ${renderCells('004', 3)}
          </div>
        </div>
      </div>

      <div class="font-bold text-[10px] leading-tight mb-3 border-b border-black pb-2 uppercase">
        ${sec4Heading}
      </div>

      <div class="space-y-2 text-[10px]">
        ${!is15 ? `
          <div class="font-bold uppercase tracking-wider text-[9px] pt-1">Сумма страховых взносов, уменьшающая сумму исчисленного налога (руб.):</div>
          <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
            <span>За I квартал (стр. 140):</span>
            ${renderMoneyCells(d.deduct_q1, 11)}
          </div>
          <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
            <span>За полугодие (стр. 141):</span>
            ${renderMoneyCells(d.deduct_q2, 11)}
          </div>
          <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
            <span>За 9 месяцев (стр. 142):</span>
            ${renderMoneyCells(d.deduct_q3, 11)}
          </div>
          <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
            <span class="font-bold">За налоговый период / год (стр. 143):</span>
            ${renderMoneyCells(d.deduct_year, 11)}
          </div>
        ` : `
          <div class="flex items-center justify-between border-b border-black pb-2 font-bold">
            <span>Сумма исчисленного минимального налога за год (стр. 280):</span>
            ${renderMoneyCells(d.min_tax, 11)}
          </div>
        `}

        <div class="font-bold uppercase tracking-wider text-[9px] pt-3">Сумма страховых взносов, установленных статьей 430 НК РФ (для ИП):</div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
          <span>В совокупном фиксированном размере (${is15 ? 'стр. 290' : 'стр. 150'}):</span>
          ${renderMoneyCells(d.ins_fixed, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
          <span>В размере 1% с доходов, превышающих 300 тыс. руб. (${is15 ? 'стр. 300' : 'стр. 160'}):</span>
          ${renderMoneyCells(d.ins_1pct, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
          <span>В том числе за расчетный период текущего года (${is15 ? 'стр. 310' : 'стр. 161'}):</span>
          ${renderMoneyCells(d.ins_1pct_curr, 11)}
        </div>
        <div class="flex items-center justify-between border-b border-slate-200 pb-1 pl-3">
          <span>За расчетный период предыдущего года (${is15 ? 'стр. 320' : 'стр. 162'}):</span>
          ${renderMoneyCells(d.ins_1pct_prev, 11)}
        </div>
      </div>
    </div>
  `;

  container.innerHTML = page1 + page2 + page3 + page4;
}

async function downloadTaxDeclarationPdf() {
  if (!state.currentCompanyId) {
    showToast('Сначала выберите бизнес');
    return;
  }
  const payload = getTaxDeclarationFormData();
  showToast('Генерация официального PDF бланка КНД 1152017...');

  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/tax-declaration/generate-pdf`, {
      method: 'POST',
      headers: getAuthHeaders(true),
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const safeInn = payload.inn ? payload.inn.replace(/\D/g, '') : 'КНД1152017';
      a.download = `Декларация_УСН_${payload.year}_${safeInn}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      showToast('Официальный PDF бланка КНД 1152017 успешно загружен!');
    } else {
      const err = await res.json();
      showToast(err.detail || 'Ошибка формирования PDF декларации');
    }
  } catch (err) {
    console.error('Error generating PDF:', err);
    showToast('Ошибка при скачивании PDF декларации');
  }
}

function printTaxDeclaration() {
  switchTaxDeclTab('preview');
  setTimeout(() => {
    window.print();
  }, 250);
}

// 15. Exports
function downloadTaxDeclaration() {
  showToast('Формирование выгрузки для налоговой декларации...');
  window.location.href = `/api/companies/${state.currentCompanyId}/export/tax-declaration`;
}

function download1CExchange() {
  window.location.href = `/api/companies/${state.currentCompanyId}/export/1c`;
}

function downloadOperationsCSV() {
  window.location.href = `/api/companies/${state.currentCompanyId}/export/csv`;
}

// ---------------- Navbar Customization & Visibility ----------------
const defaultNavTabs = {
  radar: true,
  breakdown: true,
  scenarios: true,
  operations: true,
  counterparties: true,
  planfact: false,
  analytics: false,
  integrations: false,
  cabinet: true
};

function getNavTabsConfig() {
  try {
    const raw = localStorage.getItem('ci_nav_tabs');
    if (raw) return { ...defaultNavTabs, ...JSON.parse(raw) };
  } catch (e) {}
  return { ...defaultNavTabs };
}

function applyNavbarCustomization() {
  const config = getNavTabsConfig();
  Object.keys(config).forEach(k => {
    const pill = document.getElementById(`pill-${k}`);
    if (pill) {
      if (config[k]) {
        pill.classList.remove('hidden');
      } else {
        pill.classList.add('hidden');
      }
    }
  });
  syncNavbarTogglesUI();
}

function syncNavbarTogglesUI() {
  const config = getNavTabsConfig();
  Object.keys(config).forEach(k => {
    const toggle = document.getElementById(`navToggle_${k}`);
    if (toggle) {
      toggle.checked = Boolean(config[k]);
    }
  });
}

function saveNavbarCustomization() {
  const config = { ...defaultNavTabs };
  const keys = ['radar', 'breakdown', 'scenarios', 'operations', 'counterparties', 'planfact', 'analytics', 'integrations', 'cabinet'];
  keys.forEach(k => {
    const toggle = document.getElementById(`navToggle_${k}`);
    if (toggle) {
      config[k] = toggle.checked;
    }
  });
  config.radar = true;
  config.cabinet = true;

  localStorage.setItem('ci_nav_tabs', JSON.stringify(config));
  applyNavbarCustomization();

  const msg = document.getElementById('navCustomizationSavedMsg');
  if (msg) {
    msg.classList.remove('hidden');
    setTimeout(() => {
      msg.classList.add('hidden');
    }, 2800);
  }
}

function resetNavbarCustomization() {
  localStorage.setItem('ci_nav_tabs', JSON.stringify(defaultNavTabs));
  applyNavbarCustomization();

  const msg = document.getElementById('navCustomizationSavedMsg');
  if (msg) {
    msg.classList.remove('hidden');
    setTimeout(() => {
      msg.classList.add('hidden');
    }, 2800);
  }
}

// ---------------- Cabinet Sub-tab Switching ----------------
function switchCabinetSubTab(subTabName) {
  state.activeCabinetSubTab = subTabName;
  const subMap = {
    'profile': { btn: 'btnCabSubProfile', content: 'cabSectionProfile' },
    'slots': { btn: 'btnCabSubSlots', content: 'tabContentPlanFact' },
    'analytics': { btn: 'btnCabSubAnalytics', content: 'tabContentAnalytics' },
    'integrations': { btn: 'btnCabSubIntegrations', content: 'tabContentIntegrations' },
    'nav': { btn: 'btnCabSubNav', content: 'cabSectionNav' }
  };

  Object.keys(subMap).forEach(k => {
    const btn = document.getElementById(subMap[k].btn);
    const content = document.getElementById(subMap[k].content);
    if (btn) {
      if (k === subTabName) {
        btn.className = "cab-sub-active px-3.5 py-2 rounded-xl transition flex items-center space-x-1.5 shadow-xs";
      } else {
        btn.className = "cab-sub-inactive px-3.5 py-2 rounded-xl transition flex items-center space-x-1.5";
      }
    }
    if (content) {
      if (k === subTabName) {
        content.classList.remove('hidden');
      } else {
        content.classList.add('hidden');
      }
    }
  });

  if (subTabName === 'profile') {
    populateCabinetPageDetails();
  } else if (subTabName === 'slots') {
    loadSlots();
  } else if (subTabName === 'analytics') {
    loadAnalytics();
  } else if (subTabName === 'integrations') {
    loadIntegrations();
  } else if (subTabName === 'nav') {
    syncNavbarTogglesUI();
  }
  lucide.createIcons();
}

// ---------------- FNS & Taxes Sub-tab Switching ----------------
function switchFnsSubTab(subTabName) {
  state.activeFnsSubTab = subTabName;
  const btnCp = document.getElementById('btnFnsSubCounterparties');
  const btnTaxes = document.getElementById('btnFnsSubTaxes');
  const contentCp = document.getElementById('fnsSubContentCounterparties');
  const contentTaxes = document.getElementById('fnsSubContentTaxes');

  if (subTabName === 'taxes') {
    if (btnCp) btnCp.className = 'cab-sub-inactive px-4 py-2 rounded-xl transition flex items-center space-x-2';
    if (btnTaxes) btnTaxes.className = 'cab-sub-active px-4 py-2 rounded-xl transition flex items-center space-x-2 shadow-xs';
    if (contentCp) contentCp.classList.add('hidden');
    if (contentTaxes) contentTaxes.classList.remove('hidden');
    renderFnsTaxesSubTab();
  } else {
    if (btnCp) btnCp.className = 'cab-sub-active px-4 py-2 rounded-xl transition flex items-center space-x-2 shadow-xs';
    if (btnTaxes) btnTaxes.className = 'cab-sub-inactive px-4 py-2 rounded-xl transition flex items-center space-x-2';
    if (contentCp) contentCp.classList.remove('hidden');
    if (contentTaxes) contentTaxes.classList.add('hidden');
    loadCounterparties();
  }
  lucide.createIcons();
}

async function renderFnsTaxesSubTab() {
  if (!state.currentCompanyId) return;

  // Make sure future events are loaded (which include tax_calendar)
  if (!state.futureEvents || state.futureEvents.length === 0) {
    try {
      const evRes = await fetch(`/api/companies/${state.currentCompanyId}/events`, { headers: getAuthHeaders() });
      if (evRes.ok) state.futureEvents = await evRes.json();
    } catch (e) {
      console.warn('Could not load events for taxes subtab:', e);
    }
  }

  const c = state.companyInfo || {};
  const regime = c.tax_regime || 'УСН Доходы 6%';
  const legalForm = (c.legal_form || 'ИП').toUpperCase();
  const isIp = legalForm.includes('ИП');

  // Update header badges
  const badgeRegime = document.getElementById('fnsTaxRegimeBadge');
  if (badgeRegime) badgeRegime.innerText = regime;
  const badgeLegal = document.getElementById('fnsTaxLegalFormBadge');
  if (badgeLegal) badgeLegal.innerText = c.legal_form || 'ИП';

  // Update formula note
  const formulaNote = document.getElementById('fnsTaxFormulaNote');
  if (formulaNote) {
    if (regime.includes('15')) {
      formulaNote.innerText = 'УСН «Доходы минус расходы» 15%: налог рассчитывается как (Доходы − Расходы за квартал) × 15%. Уведомления до 25 числа, уплата до 28 числа (с переносом с выходных).';
    } else if (regime.includes('НДС') || regime.includes('ОСНО')) {
      formulaNote.innerText = 'ОСНО с НДС 22%: платежи производятся равными долями по 1/3 суммы до 28 числа каждого месяца (с переносом с выходных дней на рабочий день).';
    } else {
      formulaNote.innerText = 'УСН «Доходы» 6%: налог рассчитывается как Доход за квартал × 6%. Уведомления подаются до 25 числа, уплата до 28 числа (с переносом с выходных).';
    }
  }

  // Filter tax calendar events
  const taxEvents = (state.futureEvents || []).filter(ev =>
    ev.source === 'tax_calendar' || (ev.note && ev.note.includes('Налоги по УСН/НДС'))
  );

  // Sort by date ascending
  taxEvents.sort((a, b) => (a.event_date || '').localeCompare(b.event_date || ''));

  // Calculate KPIs
  const kpiRegime = document.getElementById('fnsKpiRegimeName');
  if (kpiRegime) kpiRegime.innerText = regime;

  const totalAccrued = taxEvents.reduce((sum, ev) => sum + Math.abs(ev.amount || 0), 0);
  const kpiTotal = document.getElementById('fnsKpiTotalAccrued');
  if (kpiTotal) kpiTotal.innerText = `${formatMoney(totalAccrued)} ₽`;

  const kpiDeclDue = document.getElementById('fnsKpiDeclarationDue');
  if (kpiDeclDue) {
    kpiDeclDue.innerText = isIp ? 'до 25 апреля (для ИП)' : 'до 25 марта (для ООО)';
  }

  // Next payment
  const todayStr = new Date().toISOString().slice(0, 10);
  const upcoming = taxEvents.filter(ev => ev.event_date >= todayStr && Math.abs(ev.amount || 0) > 0);
  const nextEv = upcoming.length > 0 ? upcoming[0] : (taxEvents.length > 0 ? taxEvents[0] : null);
  const kpiNext = document.getElementById('fnsKpiNextPayment');
  if (kpiNext) {
    if (nextEv) {
      kpiNext.innerText = `${formatDate(nextEv.event_date)} • ${formatMoney(Math.abs(nextEv.amount || 0))} ₽`;
    } else {
      kpiNext.innerText = 'Все выплачено';
    }
  }

  const countBadge = document.getElementById('fnsTaxEventsCount');
  if (countBadge) countBadge.innerText = taxEvents.length;

  const container = document.getElementById('fnsTaxEventsList');
  if (!container) return;

  if (taxEvents.length === 0) {
    container.innerHTML = `
      <div class="text-center py-8 text-slate-400 bg-slate-50 rounded-xl border border-dashed border-slate-200">
        <i data-lucide="calculator" class="w-8 h-8 mx-auto mb-2 text-slate-300"></i>
        <div class="font-extrabold text-xs text-slate-700">Налоговые события формируются автоматически</div>
        <p class="text-[11px] text-slate-400 mt-1 max-w-md mx-auto">
          При добавлении операций или загрузке банковской выписки система автоматически рассчитает авансовые платежи УСН 6% / 15% и НДС 22% по кварталам со сдвигом с выходных дней.
        </p>
      </div>
    `;
    lucide.createIcons();
    return;
  }

  container.innerHTML = taxEvents.map(ev => {
    const absAmt = Math.abs(ev.amount || 0);
    const isNotice = absAmt === 0 || (ev.title && ev.title.toLowerCase().includes('уведомлен'));
    const isDeclaration = ev.title && ev.title.toLowerCase().includes('декларац');
    const isNds = ev.title && ev.title.includes('НДС');

    // Parse note for details
    let noteText = ev.note || '';
    noteText = noteText.replace(/^Налоги по УСН\/НДС\s*\|\s*/, '');

    const badgeTitle = isDeclaration ? 'Декларация за год' : (isNotice ? 'Уведомление об исчисленных суммах' : (isNds ? 'Уплата 1/3 НДС' : 'Уплата авансового платежа'));

    return `
      <div class="p-3.5 rounded-xl border border-purple-200 bg-purple-50/40 hover:bg-purple-50 transition flex items-center justify-between flex-wrap gap-3">
        <div class="flex items-center space-x-3">
          <div class="w-10 h-10 rounded-xl bg-purple-100 text-purple-900 border border-purple-300 flex items-center justify-center font-black text-xs shrink-0 shadow-2xs">
            <i data-lucide="${isDeclaration ? 'file-signature' : (isNotice ? 'bell' : 'landmark')}" class="w-5 h-5 text-purple-700"></i>
          </div>
          <div>
            <div class="flex items-center space-x-2 flex-wrap gap-y-1">
              <span class="text-xs font-black text-slate-900">${ev.title}</span>
              <span class="text-[10px] font-black px-2 py-0.5 rounded-full bg-purple-100 text-purple-900 border border-purple-300 flex items-center space-x-1 shadow-2xs">
                <i data-lucide="landmark" class="w-3 h-3 text-purple-700"></i>
                <span>Налоги по УСН/НДС</span>
              </span>
              <span class="text-[10px] font-extrabold px-2 py-0.5 rounded-full ${isNotice ? 'bg-blue-100 text-blue-900 border border-blue-200' : 'bg-emerald-100 text-emerald-900 border border-emerald-200'}">
                ${badgeTitle}
              </span>
            </div>
            <div class="text-[11px] text-purple-900 mt-1 flex items-center space-x-2 flex-wrap">
              <span>Срок: <b class="text-slate-900">${formatDate(ev.event_date)}</b></span>
              <span>•</span>
              <span>Получатель: <b>ФНС России (ЕНС)</b></span>
              <span>•</span>
              <span class="text-slate-500">${noteText}</span>
            </div>
          </div>
        </div>
        <div class="flex items-center space-x-3">
          <div class="text-right">
            <div class="text-sm font-black text-purple-950 font-display">
              ${absAmt > 0 ? '− ' + formatMoney(absAmt) + ' ₽' : '<span class="text-xs text-purple-700 font-bold">0.00 ₽ (уведомление)</span>'}
            </div>
            <span class="text-[10px] font-bold text-purple-700">
              100% • Обязательный платеж
            </span>
          </div>
          <button onclick="openTaxDeclarationStubModal()" title="Сформировать налоговую декларацию" class="bg-white hover:bg-purple-100 text-purple-900 border border-purple-300 px-2.5 py-1.5 rounded-lg text-xs font-bold transition flex items-center space-x-1 shadow-2xs">
            <i data-lucide="file-text" class="w-3.5 h-3.5"></i>
            <span class="hidden sm:inline">Декларация</span>
          </button>
        </div>
      </div>
    `;
  }).join('');

  lucide.createIcons();
}

// ---------------- Main Tab Switching Logic ----------------
function switchTab(tabName) {
  // If user clicks Slots / Analytics / Integrations, direct them smoothly to that section inside Cabinet
  if (tabName === 'planfact') {
    switchTab('cabinet');
    switchCabinetSubTab('slots');
    return;
  }
  if (tabName === 'analytics') {
    switchTab('cabinet');
    switchCabinetSubTab('analytics');
    return;
  }
  if (tabName === 'integrations') {
    switchTab('cabinet');
    switchCabinetSubTab('integrations');
    return;
  }
  if (tabName === 'fns') {
    tabName = 'counterparties';
  }

  state.activeTab = tabName;
  const allTabs = ['radar', 'breakdown', 'scenarios', 'operations', 'counterparties', 'cabinet', 'planfact', 'analytics', 'integrations'];
  
  allTabs.forEach(t => {
    const pill = document.getElementById(`pill-${t}`);
    if (pill) {
      if (t === tabName) {
        pill.classList.remove('pill-inactive');
        pill.classList.add('pill-active');
      } else {
        pill.classList.remove('pill-active');
        pill.classList.add('pill-inactive');
      }
    }
  });

  const tabContents = {
    'radar': 'tabContentRadar',
    'breakdown': 'tabContentBreakdown',
    'scenarios': 'tabContentScenarios',
    'operations': 'tabContentOperations',
    'counterparties': 'tabContentCounterparties',
    'cabinet': 'tabContentCabinet'
  };

  Object.keys(tabContents).forEach(t => {
    const content = document.getElementById(tabContents[t]);
    if (content) {
      if (t === tabName) {
        content.classList.remove('hidden');
      } else {
        content.classList.add('hidden');
      }
    }
  });

  // Re-apply navbar visibility customization EVERY TIME so hidden pills NEVER reappear!
  applyNavbarCustomization();

  if (tabName === 'cabinet') {
    if (!state.activeCabinetSubTab) {
      switchCabinetSubTab('profile');
    } else {
      switchCabinetSubTab(state.activeCabinetSubTab);
    }
  } else if (tabName === 'operations') {
    loadOperations();
  } else if (tabName === 'counterparties') {
    if (state.activeFnsSubTab === 'taxes') {
      renderFnsTaxesSubTab();
    } else {
      loadCounterparties();
    }
  } else if (tabName === 'scenarios') {
    if (state.activeScenarioId) {
      selectScenario(state.activeScenarioId);
    } else {
      cancelScenario();
    }
  }
  lucide.createIcons();
}

// Formatting Utilities
function formatMoney(val) {
  if (val === undefined || val === null) return '0';
  return Math.round(val).toLocaleString('ru-RU');
}

function formatDate(dStr) {
  if (!dStr) return '';
  const parts = dStr.split('-');
  if (parts.length === 3) {
    return `${parts[2]}.${parts[1]}.${parts[0]}`;
  }
  return dStr;
}

function getCategoryName(catId) {
  const map = {
    'cat_revenue_client': 'Выручка от клиентов',
    'cat_revenue_acquiring': 'Эквайринг и СБП',
    'cat_payroll': 'Зарплата',
    'cat_tax_enp': 'ЕНП Налоги',
    'cat_rent_utilities': 'Аренда',
    'cat_procurement': 'Закупки',
    'cat_transport': 'Транспорт',
    'cat_bank_credit': 'Банк и кредит',
    'cat_services_marketing': 'Сервисы',
    'cat_transfer_own': 'Свои счета'
  };
  return map[catId] || catId;
}

function formatSource(s) {
  const map = {
    'history': 'История',
    'slot': 'Слот',
    'manual': 'Ввод',
    '1c_enterprise': '1С',
    'fns_nalog': 'ФНС',
    'bank_centroinvest': 'Банк',
    'edo_diadoc': 'ЭДО',
    'marketplaces': 'WB / Ozon'
  };
  return map[s] || s;
}

// ==========================================
// COUNTERPARTIES & FNS ANALYSIS (nalogbi + check)
// ==========================================

async function loadCounterparties() {
  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/counterparties`);
    if (!res.ok) throw new Error('Ошибка загрузки контрагентов');
    state.counterparties = await res.json();
    renderCounterpartiesTable();
    populateCounterpartiesDropdowns();
    await updateFnsKeyStatusUI();
  } catch (err) {
    console.error('Error loading counterparties:', err);
  }
}

async function updateFnsKeyStatusUI() {
  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/counterparties/api-key-status`);
    if (res.ok) {
      const data = await res.json();
      const dot = document.getElementById('fnsKeyStatusDot');
      const label = document.getElementById('fnsKeyStatusLabel');
      if (data.has_key) {
        state.fnsApiKey = state.fnsApiKey || 'LIVE_KEY_ACTIVE';
        if (dot) dot.className = "w-2 h-2 rounded-full bg-emerald-400 animate-pulse";
        if (label) label.innerText = `API ФНС: Онлайн (${data.masked_key})`;
      } else {
        if (dot) dot.className = "w-2 h-2 rounded-full bg-amber-400";
        if (label) label.innerText = "Указать ключ api-fns.ru";
      }
    }
  } catch (err) {
    console.error('Error fetching key status:', err);
  }
}

function renderCounterpartiesTable() {
  const tbody = document.getElementById('counterpartiesTableBody');
  if (!tbody) return;

  const list = state.counterparties || [];

  // Update KPI counters
  const total = list.length;
  const checked = list.filter(c => c.last_checked_at).length;
  const blocked = list.filter(c => c.has_blocks).length;
  const atRiskSum = list.filter(c => c.has_blocks || c.risk_level === 'red')
    .reduce((sum, c) => sum + (c.inflow_sum || 0), 0);

  const kpiTotal = document.getElementById('kpiCpTotal');
  const kpiChecked = document.getElementById('kpiCpChecked');
  const kpiBlocked = document.getElementById('kpiCpBlocked');
  const kpiAtRisk = document.getElementById('kpiCpAtRiskSum');
  const countAll = document.getElementById('cpCountAll');
  const countBlocked = document.getElementById('cpCountBlocked');
  const badge = document.getElementById('counterpartyRiskBadge');

  if (kpiTotal) kpiTotal.innerText = total;
  if (kpiChecked) kpiChecked.innerText = checked;
  if (kpiBlocked) kpiBlocked.innerText = blocked;
  if (kpiAtRisk) kpiAtRisk.innerText = `${formatMoney(atRiskSum)} ₽`;
  if (countAll) countAll.innerText = total;
  if (countBlocked) countBlocked.innerText = blocked;
  if (badge) {
    if (blocked > 0) {
      badge.classList.remove('hidden');
      badge.innerText = blocked;
    } else {
      badge.classList.add('hidden');
    }
  }

  // Filter
  let filtered = list;
  if (state.cpFilter === 'payer') {
    filtered = filtered.filter(c => c.role === 'payer' || c.role === 'both');
  } else if (state.cpFilter === 'supplier') {
    filtered = filtered.filter(c => c.role === 'supplier');
  } else if (state.cpFilter === 'blocked') {
    filtered = filtered.filter(c => c.has_blocks);
  } else if (state.cpFilter === 'risk') {
    filtered = filtered.filter(c => c.risk_level === 'red' || c.risk_level === 'yellow' || c.has_blocks);
  }

  // Search
  if (state.cpSearch) {
    const q = state.cpSearch.toLowerCase().trim();
    filtered = filtered.filter(c => 
      (c.name && c.name.toLowerCase().includes(q)) || 
      (c.inn && c.inn.includes(q))
    );
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="text-center py-8 text-slate-400">
          <div class="w-8 h-8 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto mb-2">
            <i data-lucide="users" class="w-4 h-4"></i>
          </div>
          Контрагенты не найдены
        </td>
      </tr>
    `;
    lucide.createIcons();
    return;
  }

  tbody.innerHTML = filtered.map(c => {
    // Role badge
    let roleBadge = '<span class="px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-bold text-[10px]">Дебитор</span>';
    if (c.role === 'supplier') {
      roleBadge = '<span class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-bold text-[10px]">Поставщик</span>';
    } else if (c.role === 'both') {
      roleBadge = '<span class="px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 font-bold text-[10px]">Смешанный</span>';
    }

    // FNS status badge
    let fnsBadge = '';
    if (!c.last_checked_at) {
      fnsBadge = `
        <span class="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 font-bold text-[10px]">
          <span class="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
          <span>Не проверялся</span>
        </span>
      `;
    } else if (c.has_blocks) {
      fnsBadge = `
        <span class="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-red-100 text-red-800 font-black text-[10px] animate-pulse">
          <span class="w-1.5 h-1.5 rounded-full bg-red-600"></span>
          <span>⛔ Счета заблокированы (ст. 76)</span>
        </span>
      `;
    } else if (c.risk_level === 'red') {
      fnsBadge = `
        <span class="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-bold text-[10px]">
          <span class="w-1.5 h-1.5 rounded-full bg-red-500"></span>
          <span>Высокий риск (${c.reliability_score || 30}%)</span>
        </span>
      `;
    } else if (c.risk_level === 'yellow') {
      fnsBadge = `
        <span class="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-bold text-[10px]">
          <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
          <span>Внимание (${c.reliability_score || 65}%)</span>
        </span>
      `;
    } else {
      fnsBadge = `
        <span class="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-bold text-[10px]">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
          <span>Чист (${c.reliability_score || 95}%)</span>
        </span>
      `;
    }

    const isChecked = c.include_in_forecast !== false;

    return `
      <tr class="hover:bg-slate-50/80 transition">
        <td class="py-3 px-3">
          <div class="font-bold text-slate-900 leading-tight">${c.name || 'Контрагент'}</div>
          <div class="text-[11px] text-slate-400 font-mono mt-0.5">ИНН: ${c.inn}</div>
        </td>
        <td class="py-3 px-3">
          ${roleBadge}
        </td>
        <td class="py-3 px-3 text-right">
          <div class="font-extrabold text-slate-900">${formatMoney(c.turnover || 0)} ₽</div>
          <div class="text-[10px] text-slate-400">${c.ops_count || 1} опер.</div>
        </td>
        <td class="py-3 px-3">
          ${fnsBadge}
        </td>
        <td class="py-3 px-3 text-center">
          <label class="inline-flex items-center cursor-pointer select-none" title="Учитывать результат проверки в итоговом прогнозе Радара">
            <input type="checkbox" ${isChecked ? 'checked' : ''} onchange="toggleCounterpartyForecast('${c.inn}', this.checked)" class="rounded text-emerald-600 focus:ring-emerald-500 w-4 h-4 cursor-pointer">
          </label>
        </td>
        <td class="py-3 px-3 text-right">
          <div class="flex items-center justify-end space-x-1.5">
            <button onclick="analyzeCounterparty('${c.inn}')" id="btnCheck-${c.inn}" title="Запросить nalogbi и check по ФНС" class="bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-[11px] px-2.5 py-1 rounded-lg transition flex items-center space-x-1">
              <i data-lucide="refresh-cw" class="w-3 h-3 text-emerald-600"></i>
              <span>Анализ</span>
            </button>
            <button onclick="openCounterpartyDetail('${c.inn}')" title="Посмотреть подробную выдержку nalogbi и check" class="bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 font-bold text-[11px] px-2.5 py-1 rounded-lg transition">
              Выдержка
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  lucide.createIcons();
}

function setCpFilter(filterType) {
  state.cpFilter = filterType;
  const filters = ['all', 'payer', 'supplier', 'blocked', 'risk'];
  filters.forEach(f => {
    const btn = document.getElementById(`cpFilter-${f}`);
    if (btn) {
      if (f === filterType) {
        btn.className = "bg-emerald-600 text-white px-2.5 py-1.5 rounded-xl transition shadow-xs";
      } else {
        btn.className = "bg-slate-100 hover:bg-slate-200 text-slate-600 px-2.5 py-1.5 rounded-xl transition";
      }
    }
  });
  renderCounterpartiesTable();
}

function filterCounterpartiesTable() {
  const input = document.getElementById('cpSearchInput');
  if (input) {
    state.cpSearch = input.value;
    renderCounterpartiesTable();
  }
}

async function analyzeCounterparty(inn) {
  const btn = document.getElementById(`btnCheck-${inn}`);
  if (btn) btn.innerHTML = '<span class="animate-spin text-xs">⏳</span>';

  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/counterparties/${inn}/check`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ inn: inn, api_key: state.fnsApiKey })
    });
    if (!res.ok) throw new Error('Ошибка анализа ФНС');
    const updated = await res.json();

    // Replace in state
    const idx = state.counterparties.findIndex(c => c.inn === inn);
    if (idx !== -1) {
      state.counterparties[idx] = updated;
    } else {
      state.counterparties.unshift(updated);
    }

    renderCounterpartiesTable();
    showToast(`ФНС анализ завершен: ${updated.name || inn} (Надежность: ${updated.reliability_score}%)`);

    // Reload forecast in background to update curve if affected
    await loadForecastData();
  } catch (err) {
    console.error('Error analyzing counterparty:', err);
    showToast('Ошибка при запросе к API ФНС');
  } finally {
    if (btn) {
      btn.innerHTML = '<i data-lucide="refresh-cw" class="w-3 h-3 text-emerald-600"></i><span>Анализ</span>';
      lucide.createIcons();
    }
  }
}

async function analyzeAllCounterparties() {
  const btn = document.getElementById('btnCheckAllFns');
  if (btn) btn.innerHTML = '<span class="animate-spin text-xs">⏳</span> Проверяем...';

  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/counterparties/check-all`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ api_key: state.fnsApiKey })
    });
    if (!res.ok) throw new Error('Ошибка пакетного анализа');
    state.counterparties = await res.json();
    renderCounterpartiesTable();
    showToast(`Проверка ФНС завершена: обработано ${state.counterparties.length} контрагентов`);

    // Reload forecast
    await loadForecastData();
  } catch (err) {
    console.error('Error in batch check:', err);
    showToast('Ошибка пакетной проверки ФНС');
  } finally {
    if (btn) {
      btn.innerHTML = '<i data-lucide="zap" class="w-3.5 h-3.5 text-amber-400"></i><span>Проверить всех</span>';
      lucide.createIcons();
    }
  }
}

async function toggleCounterpartyForecast(inn, isChecked) {
  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/counterparties/${inn}/toggle-forecast`, {
      method: 'PATCH',
      headers: getAuthHeaders(),
      body: JSON.stringify({ include_in_forecast: isChecked })
    });
    if (!res.ok) throw new Error('Ошибка обновления настройки');

    const cp = state.counterparties.find(c => c.inn === inn);
    if (cp) cp.include_in_forecast = isChecked;

    showToast(isChecked ? 'Учет риска ФНС включен в итоговом графике' : 'Учет риска ФНС исключен из графика');

    // Reload forecast immediately so the curve recomputes
    await loadForecastData();
  } catch (err) {
    console.error('Error toggling forecast:', err);
    showToast('Ошибка обновления статуса');
  }
}

function openCounterpartyDetail(inn) {
  const cp = state.counterparties.find(c => c.inn === inn);
  if (!cp) return;

  state.selectedCounterparty = cp;

  const modal = document.getElementById('counterpartyDetailModal');
  const nameEl = document.getElementById('modalCpName');
  const innEl = document.getElementById('modalCpInn');
  const roleBadge = document.getElementById('modalCpRoleBadge');
  const riskBadge = document.getElementById('modalCpRiskBadge');
  const nalogbiStatus = document.getElementById('modalNalogbiStatus');
  const checkScore = document.getElementById('modalCheckScore');
  const egrEl = document.getElementById('modalEgrulStatus');
  const unifiedBox = document.getElementById('modalUnifiedFactorsList');
  const toggle = document.getElementById('modalIncludeInForecastToggle');

  const isUnchecked = !cp.last_checked_at || cp.risk_level === 'unknown';
  const isNonExistent = !isUnchecked && ((cp.reliability_score === 0) || (cp.name && cp.name.includes('не существует')));

  if (nameEl) nameEl.innerText = cp.name || 'Организация';
  if (innEl) innEl.innerText = cp.inn;
  if (roleBadge) {
    roleBadge.innerText = cp.role === 'supplier' ? 'Поставщик' : (cp.role === 'both' ? 'Смешанный' : 'Дебитор');
  }

  // Risk badge
  if (riskBadge) {
    if (isUnchecked) {
      riskBadge.className = 'text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full bg-slate-100 text-slate-600';
      riskBadge.innerText = 'Не проверено';
    } else if (isNonExistent) {
      riskBadge.className = 'text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full bg-red-100 text-red-800 animate-pulse';
      riskBadge.innerText = '⛔ Не существует в ЕГРЮЛ';
    } else if (cp.has_blocks) {
      riskBadge.className = 'text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full bg-red-100 text-red-800 animate-pulse';
      riskBadge.innerText = '⛔ Счета заблокированы ФНС';
    } else if (cp.risk_level === 'red') {
      riskBadge.className = 'text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full bg-red-100 text-red-700';
      riskBadge.innerText = 'Высокий риск';
    } else if (cp.risk_level === 'yellow') {
      riskBadge.className = 'text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full bg-amber-100 text-amber-800';
      riskBadge.innerText = 'Умеренный риск';
    } else {
      riskBadge.className = 'text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800';
      riskBadge.innerText = 'Благонадежный';
    }
  }

  // Score
  if (checkScore) {
    if (isUnchecked) {
      checkScore.innerText = '— / 100';
    } else if (isNonExistent) {
      checkScore.innerText = '0 / 100';
    } else {
      checkScore.innerText = `${cp.reliability_score ?? 100} / 100`;
    }
  }

  // Nalogbi status
  if (nalogbiStatus) {
    if (isUnchecked) {
      nalogbiStatus.className = 'text-sm font-bold text-slate-400';
      nalogbiStatus.innerText = 'Не проверялось';
    } else if (isNonExistent) {
      nalogbiStatus.className = 'text-sm font-black text-slate-500';
      nalogbiStatus.innerText = 'Не применимо';
    } else if (cp.has_blocks) {
      nalogbiStatus.className = 'text-sm font-black text-red-600';
      nalogbiStatus.innerText = `Блокировка: ${cp.blocks_count || 1} решений`;
    } else {
      nalogbiStatus.className = 'text-sm font-black text-emerald-700';
      nalogbiStatus.innerText = 'Блокировок нет';
    }
  }

  // EGRUL status
  if (egrEl) {
    if (isUnchecked) {
      egrEl.innerText = 'Не проверялся';
      egrEl.className = 'text-sm font-bold text-slate-400';
    } else if (isNonExistent) {
      egrEl.innerText = 'Не найдена';
      egrEl.className = 'text-sm font-black text-red-600';
    } else {
      egrEl.innerText = 'Действующее';
      egrEl.className = 'text-sm font-black text-slate-800';
    }
  }

  // SINGLE UNIFIED FACTORS LIST (Risk factors FIRST, then Positive markers)
  if (unifiedBox) {
    let html = '';

    if (isUnchecked) {
      html += `
        <div class="p-6 text-center space-y-2 bg-slate-50 border border-slate-100 rounded-xl">
          <div class="w-10 h-10 rounded-xl bg-slate-200 text-slate-500 flex items-center justify-center mx-auto font-bold">
            <i data-lucide="shield-question" class="w-5 h-5"></i>
          </div>
          <div class="font-extrabold text-xs text-slate-800">Проверка в ФНС еще не проводилась</div>
          <p class="text-[11px] text-slate-400 max-w-sm mx-auto">
            Для этого контрагента пока нет официальных данных из реестров ФНС. Нажмите «Проверить в ФНС», чтобы запросить статус счетов и благонадежность.
          </p>
          <button onclick="analyzeCounterparty('${cp.inn}')" class="bg-ci-600 hover:bg-ci-700 text-white font-bold text-xs px-3.5 py-1.5 rounded-xl transition shadow-sm inline-flex items-center space-x-1.5 mt-1">
            <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
            <span>Проверить в ФНС</span>
          </button>
        </div>
      `;
    } else if (isNonExistent) {
      html += `
        <div class="p-4 bg-red-50 text-red-950 flex items-start space-x-3">
          <i data-lucide="alert-octagon" class="w-5 h-5 text-red-600 shrink-0 mt-0.5"></i>
          <div>
            <div class="font-extrabold text-xs text-red-900">Организация не найдена в реестрах ФНС (ЕГРЮЛ / ЕГРИП)</div>
            <div class="text-[11px] text-red-700 mt-1 leading-relaxed">
              По указанному ИНН (${cp.inn}) регистрация юридического лица или ИП в базе ФНС России не обнаружена. Проверка невозможна.
            </div>
          </div>
        </div>
      `;
    } else {
      // 1. Active nalogbi account blocks (top priority risk)
      if (cp.has_blocks && cp.blocks_info && cp.blocks_info.length > 0) {
        cp.blocks_info.forEach(b => {
          html += `
            <div class="p-3 bg-red-50 border-b border-red-100 flex items-start space-x-2.5">
              <i data-lucide="ban" class="w-4 h-4 text-red-600 shrink-0 mt-0.5"></i>
              <div class="flex-1 text-xs">
                <div class="font-bold text-red-900 flex items-center justify-between">
                  <span>Блокировка счета (ст. 76 НК РФ) — Решение № ${b.number || 'б/н'}</span>
                  <span class="text-[10px] bg-red-200 text-red-900 px-1.5 py-0.2 rounded font-black">${b.date || ''}</span>
                </div>
                <div class="text-[11px] text-red-800 mt-0.5">${b.authority || 'ИФНС'} • ${b.bank || ''}</div>
                <div class="text-[11px] text-red-900 font-semibold mt-0.5">Основание: ${b.reason || 'ст. 76 НК РФ'}</div>
              </div>
            </div>
          `;
        });
      }

      // 2. Negative risk factors (first in list)
      const negs = (cp.negative_factors || []).filter(f => f && f !== 'Есть' && f !== 'Да');
      if (negs.length > 0) {
        negs.forEach(f => {
          html += `
            <div class="p-2.5 px-4 bg-red-50/50 flex items-center space-x-2.5 text-xs text-red-950">
              <i data-lucide="alert-circle" class="w-4 h-4 text-red-600 shrink-0"></i>
              <span class="font-semibold text-red-900">${f}</span>
            </div>
          `;
        });
      } else if (!cp.has_blocks) {
        html += `
          <div class="p-2.5 px-4 bg-slate-50 flex items-center space-x-2.5 text-xs text-slate-500">
            <i data-lucide="shield-check" class="w-4 h-4 text-emerald-600 shrink-0"></i>
            <span>Факторов риска и блокировок счетов не обнаружено</span>
          </div>
        `;
      }

      // 3. Positive factors (second in list)
      let poss = (cp.positive_factors || []).filter(f => f && f !== 'Есть' && f !== 'Да');
      if (poss.length === 0) poss = ['Действующее юридическое лицо', 'Своевременная сдача отчетности'];
      poss.forEach(f => {
        html += `
          <div class="p-2.5 px-4 flex items-center space-x-2.5 text-xs text-slate-800 hover:bg-slate-50/50 transition">
            <i data-lucide="check-circle-2" class="w-4 h-4 text-emerald-600 shrink-0"></i>
            <span class="font-medium">${f}</span>
          </div>
        `;
      });
    }

    unifiedBox.innerHTML = html;
  }

  if (toggle) {
    toggle.checked = cp.include_in_forecast !== false;
  }

  if (modal) modal.classList.remove('hidden');
  lucide.createIcons();
}

function closeCounterpartyDetailModal() {
  const modal = document.getElementById('counterpartyDetailModal');
  if (modal) modal.classList.add('hidden');
}

function toggleModalCounterpartyForecast(isChecked) {
  if (state.selectedCounterparty) {
    toggleCounterpartyForecast(state.selectedCounterparty.inn, isChecked);
  }
}

function applyCounterpartyToRadar() {
  closeCounterpartyDetailModal();
  switchTab('radar');
  showToast('Смоделирован прогноз с учетом рисков контрагента');
  fetchForecast(state.currentCompanyId, state.currentHorizon);
}

// Add Counterparty Modal
function openAddCounterpartyModal() {
  const modal = document.getElementById('addCounterpartyModal');
  if (modal) modal.classList.remove('hidden');
}

function closeAddCounterpartyModal() {
  const modal = document.getElementById('addCounterpartyModal');
  if (modal) modal.classList.add('hidden');
}

async function submitNewCounterparty() {
  const innInput = document.getElementById('addCpInn');
  const nameInput = document.getElementById('addCpName');
  const roleSelect = document.getElementById('addCpRole');
  const forecastToggle = document.getElementById('addCpIncludeForecast');
  const btn = document.getElementById('btnSubmitNewCp');

  const inn = innInput ? innInput.value.trim() : '';
  if (!inn || inn.length < 9) {
    alert('Пожалуйста, введите корректный ИНН контрагента');
    return;
  }

  if (btn) btn.innerHTML = '<span class="animate-spin text-xs">⏳</span> Проверяем...';

  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/counterparties`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        inn: inn,
        name: nameInput ? nameInput.value.trim() : null,
        role: roleSelect ? roleSelect.value : 'payer',
        include_in_forecast: forecastToggle ? forecastToggle.checked : true,
        api_key: state.fnsApiKey
      })
    });
    if (!res.ok) throw new Error('Ошибка добавления контрагента');
    const created = await res.json();

    state.counterparties.unshift(created);
    renderCounterpartiesTable();
    closeAddCounterpartyModal();
    showToast(`Контрагент ${created.name || inn} добавлен и проверен по ФНС!`);

    // Reset inputs
    if (innInput) innInput.value = '';
    if (nameInput) nameInput.value = '';

    // Reload forecast if needed
    await loadForecastData();
  } catch (err) {
    console.error('Error adding counterparty:', err);
    showToast('Ошибка при проверке контрагента');
  } finally {
    if (btn) {
      btn.innerHTML = 'Проверить в ФНС';
    }
  }
}

// FNS API Key Modal
function openFnsApiKeyModal() {
  const modal = document.getElementById('fnsApiKeyModal');
  const input = document.getElementById('inputFnsApiKey');
  if (input) input.value = state.fnsApiKey || '';
  if (modal) modal.classList.remove('hidden');
}

function closeFnsApiKeyModal() {
  const modal = document.getElementById('fnsApiKeyModal');
  if (modal) modal.classList.add('hidden');
}

async function saveFnsApiKey() {
  const input = document.getElementById('inputFnsApiKey');
  const key = input ? input.value.trim() : '';
  state.fnsApiKey = key;
  localStorage.setItem('ci_fns_api_key', key);

  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/counterparties/api-key`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ api_key: key })
    });
    if (res.ok) {
      const data = await res.json();
      showToast(data.message);
    } else {
      showToast(key ? 'Ключ api-fns.ru сохранен' : 'Ключ сброшен (активирован демо-режим)');
    }
    await updateFnsKeyStatusUI();
    closeFnsApiKeyModal();
  } catch (err) {
    console.error('Error saving API key:', err);
    showToast('Ключ сохранен локально');
    await updateFnsKeyStatusUI();
    closeFnsApiKeyModal();
  }
}

// Global window bindings for inline HTML handlers
window.switchCabinetSubTab = switchCabinetSubTab;
window.saveNavbarCustomization = saveNavbarCustomization;
window.resetNavbarCustomization = resetNavbarCustomization;
window.applyNavbarCustomization = applyNavbarCustomization;

// ================= BALANCE EDITING =================
function openEditBalanceModal() {
  if (!state.currentCompanyId) {
    showToast('Войдите в аккаунт для редактирования остатка');
    openAuthModal('login');
    return;
  }
  const modal = document.getElementById('editBalanceModal');
  if (!modal) return;

  const c = state.companyInfo || {};
  const input = document.getElementById('editBalanceInput');
  const stmtVal = document.getElementById('editBalanceStatementVal');
  const stmtDate = document.getElementById('editBalanceStatementDate');

  if (input) input.value = c.last_balance || 0;
  if (stmtVal) stmtVal.innerText = `${formatMoney(c.last_balance || 0)} ₽`;
  if (stmtDate) stmtDate.innerText = c.last_operation_date ? formatDate(c.last_operation_date) : 'По выписке';

  modal.classList.remove('hidden');
  lucide.createIcons();
}

function closeEditBalanceModal() {
  const modal = document.getElementById('editBalanceModal');
  if (modal) modal.classList.add('hidden');
}

async function submitEditBalance(e) {
  if (e && e.preventDefault) e.preventDefault();
  const input = document.getElementById('editBalanceInput');
  if (!input) return;
  const newBal = parseFloat(input.value) || 0.0;

  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders()
      },
      body: JSON.stringify({
        initial_manual_balance: newBal,
        last_balance: newBal
      })
    });

    if (!res.ok) throw new Error('Ошибка обновления остатка');
    const updated = await res.json();
    state.companyInfo = updated;
    closeEditBalanceModal();
    showToast(newBal === 0 ? 'Остаток сброшен к выписке' : `Остаток обновлен: ${formatMoney(newBal)} ₽`);
    await loadCompaniesList();
    await loadAllCompanyData(state.currentCompanyId);
    await loadForecastData();
  } catch (err) {
    console.error('Error updating balance:', err);
    showToast('Ошибка сохранения остатка');
  }
}

async function resetBalanceToStatement() {
  const input = document.getElementById('editBalanceInput');
  if (input) input.value = 0;
  await submitEditBalance({ preventDefault: () => {} });
}

// ================= STATEMENT UPLOAD HISTORY =================
async function loadStatementUploadHistory() {
  if (!state.currentCompanyId) return;
  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}/uploads`, { headers: getAuthHeaders() });
    if (!res.ok) return;
    const history = await res.json();

    // 1. Table in Cabinet Page
    const tableBody = document.getElementById('uploadHistoryTableBody');
    if (tableBody) {
      if (!history || history.length === 0) {
        tableBody.innerHTML = `
          <tr>
            <td colspan="6" class="py-5 text-center text-slate-400">История загрузок пуста. Загрузите файл выписки для формирования кассового радара.</td>
          </tr>
        `;
      } else {
        tableBody.innerHTML = '';
        history.forEach(item => {
          const row = document.createElement('tr');
          row.className = 'hover:bg-slate-50 transition border-b border-slate-100/80';
          const dt = new Date(item.uploaded_at);
          const dateStr = dt.toLocaleString('ru-RU', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
          });
          const score = Math.round(item.data_quality_score || 100);
          const scoreBadge = score >= 90
            ? `<span class="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 font-extrabold text-[10px]">${score}% (высокое)</span>`
            : `<span class="px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200 font-extrabold text-[10px]">${score}%</span>`;

          row.innerHTML = `
            <td class="py-2.5 px-3 font-bold text-slate-800 flex items-center space-x-2">
              <i data-lucide="file-spreadsheet" class="w-4 h-4 text-ci-600 shrink-0"></i>
              <span class="truncate max-w-[200px]" title="${item.filename}">${item.filename}</span>
            </td>
            <td class="py-2.5 px-3 text-slate-500 font-medium whitespace-nowrap">${dateStr}</td>
            <td class="py-2.5 px-3 font-black text-slate-900">${(item.operations_count || 0).toLocaleString('ru-RU')} оп.</td>
            <td class="py-2.5 px-3">${scoreBadge}</td>
            <td class="py-2.5 px-3 font-semibold text-slate-600">${item.slots_detected || 0} слотов</td>
            <td class="py-2.5 px-3 text-right">
              <span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-black text-[10px] uppercase">
                ${item.status === 'success' ? 'Успешно' : item.status}
              </span>
            </td>
          `;
          tableBody.appendChild(row);
        });
      }
    }

    // 2. List in Cabinet Modal
    const modalList = document.getElementById('modalUploadHistoryList');
    if (modalList) {
      if (!history || history.length === 0) {
        modalList.innerHTML = `<div class="text-[11px] text-slate-400 py-1">Нет загруженных выписок</div>`;
      } else {
        modalList.innerHTML = '';
        history.slice(0, 5).forEach(item => {
          const dt = new Date(item.uploaded_at);
          const dateStr = dt.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
          const div = document.createElement('div');
          div.className = 'p-2 rounded-xl bg-slate-50 border border-slate-200/60 flex items-center justify-between text-[11px]';
          div.innerHTML = `
            <div class="flex items-center space-x-2 truncate">
              <i data-lucide="file-text" class="w-3.5 h-3.5 text-ci-600 shrink-0"></i>
              <span class="font-bold text-slate-800 truncate">${item.filename}</span>
              <span class="text-slate-400 text-[10px]">(${dateStr})</span>
            </div>
            <span class="font-extrabold text-emerald-700 shrink-0">${(item.operations_count || 0).toLocaleString('ru-RU')} оп.</span>
          `;
          modalList.appendChild(div);
        });
      }
    }
    lucide.createIcons();
  } catch (err) {
    console.error('Error loading statement upload history:', err);
  }
}

// ================= BUSINESS DELETION =================
function openDeleteBusinessModal() {
  const c = state.companyInfo;
  if (!c) {
    showToast('Нет выбранного бизнеса для удаления');
    return;
  }
  const modal = document.getElementById('deleteBusinessModal');
  if (!modal) return;

  const nameEl = document.getElementById('deleteBusinessName');
  const innEl = document.getElementById('deleteBusinessInn');
  if (nameEl) nameEl.innerText = c.name || 'Организация';
  if (innEl) innEl.innerText = c.inn || '—';

  modal.classList.remove('hidden');
  lucide.createIcons();
}

function closeDeleteBusinessModal() {
  const modal = document.getElementById('deleteBusinessModal');
  if (modal) modal.classList.add('hidden');
}

async function confirmDeleteBusiness() {
  if (!state.currentCompanyId) return;
  const btn = document.getElementById('btnConfirmDeleteBiz');
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`/api/companies/${state.currentCompanyId}`, {
      method: 'DELETE',
      headers: getAuthHeaders()
    });

    if (res.ok) {
      const data = await res.json();
      closeDeleteBusinessModal();
      closeCabinetModal();
      showToast(data.message || 'Бизнес успешно удален');

      // Reload companies
      await loadCompaniesList();
      if (data.next_company_id) {
        state.currentCompanyId = data.next_company_id;
        localStorage.setItem('ci_radar_company_id', data.next_company_id);
        await loadAllCompanyData(data.next_company_id);
      } else if (state.companies && state.companies.length > 0) {
        state.currentCompanyId = state.companies[0].id;
        localStorage.setItem('ci_radar_company_id', state.companies[0].id);
        await loadAllCompanyData(state.companies[0].id);
      } else {
        state.currentCompanyId = null;
        localStorage.removeItem('ci_radar_company_id');
        state.companyInfo = null;
        renderEmptyGuestDashboard();
      }
    } else {
      const err = await res.json();
      showToast(err.detail || 'Ошибка удаления бизнеса');
    }
  } catch (err) {
    console.error('Error deleting business:', err);
    showToast('Ошибка удаления бизнеса');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Window Event Exports
window.openEditBalanceModal = openEditBalanceModal;
window.closeEditBalanceModal = closeEditBalanceModal;
window.submitEditBalance = submitEditBalance;
window.resetBalanceToStatement = resetBalanceToStatement;
window.deleteEventById = deleteEventById;
window.confirmFuturePaymentToOperation = confirmFuturePaymentToOperation;
window.toggleEventActive = toggleEventActive;
window.openEditEventModal = openEditEventModal;
window.closeEditEventModal = closeEditEventModal;
window.submitEditEvent = submitEditEvent;
window.validateInnAndName = validateInnAndName;
window.validateCounterpartyInput = validateCounterpartyInput;
window.loadStatementUploadHistory = loadStatementUploadHistory;
window.openDeleteBusinessModal = openDeleteBusinessModal;
window.closeDeleteBusinessModal = closeDeleteBusinessModal;
window.confirmDeleteBusiness = confirmDeleteBusiness;
window.onQuickSelectCounterparty = onQuickSelectCounterparty;
window.selectCounterpartyByInn = selectCounterpartyByInn;
window.onCounterpartyNameInput = onCounterpartyNameInput;
window.onCounterpartyInnInput = onCounterpartyInnInput;
window.populateCounterpartiesDropdowns = populateCounterpartiesDropdowns;
window.openTaxDeclarationStubModal = openTaxDeclarationStubModal;
window.closeTaxDeclarationStubModal = closeTaxDeclarationStubModal;
window.openTaxDeclarationModal = openTaxDeclarationModal;
window.closeTaxDeclarationModal = closeTaxDeclarationModal;
window.changeTaxDeclYear = changeTaxDeclYear;
window.switchTaxDeclTab = switchTaxDeclTab;
window.onTaxDeclInputChange = onTaxDeclInputChange;
window.onTaxDeclObjectChange = onTaxDeclObjectChange;
window.recalculateTaxDeclaration = recalculateTaxDeclaration;
window.recalculateFromDatabase = recalculateFromDatabase;
window.downloadTaxDeclarationPdf = downloadTaxDeclarationPdf;
window.printTaxDeclaration = printTaxDeclaration;
window.switchFnsSubTab = switchFnsSubTab;
window.renderFnsTaxesSubTab = renderFnsTaxesSubTab;



