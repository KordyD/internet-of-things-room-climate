const chartConfig = {
  pm25: { element: 'pm25Chart', title: 'PM2.5', unit: 'ug/m3', color: '#ff7a59' },
  humidity: { element: 'humidityChart', title: 'Влажность', unit: '%', color: '#33b1ff' },
  temperature: { element: 'temperatureChart', title: 'Температура', unit: '°C', color: '#f8c146' },
  purifier_motor_speed: { element: 'motorChart', title: 'Скорость мотора', unit: 'rpm', color: '#7c5cff' },
};

const deviceLabels = {
  purifier: 'Очиститель',
  humidifier: 'Увлажнитель',
  system: 'Система',
};

const purifierModeLabels = {
  0: 'Auto',
  1: 'Sleep',
  2: 'Favorite',
};

const humidifierModeLabels = {
  1: 'Уровень 1',
  2: 'Уровень 2',
  3: 'Уровень 3',
};

const statusEl = document.querySelector('#status');
const pollNowButton = document.querySelector('#pollNow');
const presetButtons = Array.from(document.querySelectorAll('.preset-button'));
const purifierPowerToggle = document.querySelector('#purifierPowerToggle');
const humidifierPowerToggle = document.querySelector('#humidifierPowerToggle');
const purifierPm25ThresholdInput = document.querySelector('#purifierPm25Threshold');
const purifierPm25LowThresholdInput = document.querySelector('#purifierPm25LowThreshold');
const purifierAutoOnPm25EnabledInput = document.querySelector('#purifierAutoOnPm25Enabled');
const purifierAutoOffPm25EnabledInput = document.querySelector('#purifierAutoOffPm25Enabled');
const purifierFavoriteLevelInput = document.querySelector('#purifierFavoriteLevel');
const humidifierHumidityLowThresholdInput = document.querySelector('#humidifierHumidityLowThreshold');
const humidifierHumidityHighThresholdInput = document.querySelector('#humidifierHumidityHighThreshold');
const humidifierAutoOnLowHumidityEnabledInput = document.querySelector('#humidifierAutoOnLowHumidityEnabled');
const humidifierAutoOffHighHumidityEnabledInput = document.querySelector('#humidifierAutoOffHighHumidityEnabled');
const humidifierFanLevelSelect = document.querySelector('#humidifierFanLevel');
const applyPurifierSettingsButton = document.querySelector('#applyPurifierSettings');
const applyHumidifierSettingsButton = document.querySelector('#applyHumidifierSettings');
const charts = new Map();
const dirtyFields = new Set();
const pendingPowerByDevice = new Map();

let refreshTimer = null;
let dashboardRefreshSeconds = 1;
let latestSnapshot = null;

const purifierFieldIds = [
  'purifierPm25LowThreshold',
  'purifierPm25Threshold',
  'purifierAutoOnPm25Enabled',
  'purifierAutoOffPm25Enabled',
  'purifierFavoriteLevel',
];

const humidifierFieldIds = [
  'humidifierHumidityLowThreshold',
  'humidifierHumidityHighThreshold',
  'humidifierAutoOnLowHumidityEnabled',
  'humidifierAutoOffHighHumidityEnabled',
  'humidifierFanLevel',
];

function formatValue(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return '--';
  return Number(value).toFixed(Number(value) % 1 === 0 ? 0 : 1);
}

function formatClock(value) {
  if (!value) return '--';
  return new Date(value).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function formatDateTime(value) {
  if (!value) return '--';
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function latestByMetric(rows) {
  return rows.reduce((acc, row) => {
    acc[row.metric] = row;
    return acc;
  }, {});
}

function lastMeasuredAt(rows) {
  return rows.reduce((latest, row) => (!latest || row.measured_at > latest ? row.measured_at : latest), null);
}

function setStatus(message, tone = 'neutral') {
  statusEl.textContent = message;
  statusEl.dataset.tone = tone;
}

function getChart(elementId) {
  if (!window.echarts) {
    throw new Error('ECharts не загрузился.');
  }
  if (!charts.has(elementId)) {
    charts.set(elementId, echarts.init(document.getElementById(elementId), null, { renderer: 'canvas' }));
  }
  return charts.get(elementId);
}

function thresholdsFor(metric, settings) {
  if (metric === 'pm25') {
    return [
      { value: Number(settings.purifier_pm25_low_threshold), label: 'Нижний порог', color: '#1f9d7a' },
      { value: Number(settings.purifier_pm25_threshold), label: 'Верхний порог', color: '#ff7a59' },
    ];
  }
  if (metric === 'humidity') {
    return [
      { value: Number(settings.humidifier_humidity_low_threshold), label: 'Нижний порог', color: '#1f9d7a' },
      { value: Number(settings.humidifier_humidity_high_threshold), label: 'Верхний порог', color: '#ff9f43' },
    ];
  }
  return [];
}

function setNumericIfClean(input, value) {
  if (!input || dirtyFields.has(input.id) || value === undefined || value === null) return;
  input.value = value;
}

function setCheckboxIfClean(input, value) {
  if (!input || dirtyFields.has(input.id)) return;
  input.checked = Boolean(value);
}

function setSelectIfClean(input, value) {
  if (!input || dirtyFields.has(input.id) || value === undefined || value === null) return;
  input.value = String(value);
}

function markDirty(event) {
  dirtyFields.add(event.currentTarget.id);
}

function clearDirtyFields(fieldIds) {
  fieldIds.forEach((fieldId) => dirtyFields.delete(fieldId));
}

function updateOverview(rows, settings) {
  const latest = latestByMetric(rows);

  document.querySelector('#pm25').textContent = formatValue(latest.pm25?.value);
  document.querySelector('#temperature').textContent = formatValue(latest.temperature?.value);
  document.querySelector('#humidity').textContent = formatValue(latest.humidity?.value);
  document.querySelector('#pollIntervalDisplay').textContent = `${dashboardRefreshSeconds} сек`;

  const measuredAt = lastMeasuredAt(rows);
  document.querySelector('#lastMeasurement').textContent = measuredAt
    ? `Последнее измерение в ${formatClock(measuredAt)}`
    : 'Пока нет измерений';

  const automationPill = document.querySelector('#automationModePill');
  automationPill.textContent = settings.automations_enabled
    ? 'Автоматизация: сценарии активны'
    : 'Автоматизация: выключена на backend';
  automationPill.dataset.tone = settings.automations_enabled ? 'success' : 'warning';

  const commandPill = document.querySelector('#commandModePill');
  commandPill.textContent = settings.control_enabled
    ? 'Команды: отправляются на устройства'
    : 'Команды: dry-run, только журнал';
  commandPill.dataset.tone = settings.control_enabled ? 'warning' : 'neutral';
}

function updatePresetButtons(value) {
  presetButtons.forEach((button) => {
    button.classList.toggle('is-active', Number(button.dataset.seconds) === Number(value));
  });
}

function updateDeviceInputs(settings, latest) {
  setNumericIfClean(purifierPm25LowThresholdInput, settings.purifier_pm25_low_threshold);
  setNumericIfClean(purifierPm25ThresholdInput, settings.purifier_pm25_threshold);
  setCheckboxIfClean(purifierAutoOnPm25EnabledInput, settings.purifier_auto_on_pm25_enabled);
  setCheckboxIfClean(purifierAutoOffPm25EnabledInput, settings.purifier_auto_off_pm25_enabled);
  setNumericIfClean(humidifierHumidityLowThresholdInput, settings.humidifier_humidity_low_threshold);
  setNumericIfClean(humidifierHumidityHighThresholdInput, settings.humidifier_humidity_high_threshold);
  setCheckboxIfClean(humidifierAutoOnLowHumidityEnabledInput, settings.humidifier_auto_on_low_humidity_enabled);
  setCheckboxIfClean(humidifierAutoOffHighHumidityEnabledInput, settings.humidifier_auto_off_high_humidity_enabled);

  const purifierFavoriteLevel = Number(latest.purifier_favorite_level?.value);
  if (Number.isFinite(purifierFavoriteLevel)) {
    setNumericIfClean(purifierFavoriteLevelInput, Math.max(1, Math.min(15, purifierFavoriteLevel)));
  }

  const humidifierMode = Number(latest.humidifier_mode?.value);
  if (Number.isFinite(humidifierMode) && humidifierMode >= 1 && humidifierMode <= 3) {
    setSelectIfClean(humidifierFanLevelSelect, humidifierMode);
  }
}

function updateDeviceStatus(device, latest, settings) {
  const powerRow = latest[`${device}_power`];
  const statusElement = document.querySelector(`#${device}Status`);
  const hintElement = document.querySelector(`#${device}Hint`);
  const toggle = document.querySelector(`#${device}PowerToggle`);
  const isKnown = powerRow?.value !== undefined && powerRow?.value !== null;
  const isOn = Number(powerRow?.value) === 1;
  const pendingPower = pendingPowerByDevice.get(device);
  const displayPower = pendingPower ?? (isKnown ? isOn : null);

  if (pendingPower !== undefined && isKnown && pendingPower === isOn) {
    pendingPowerByDevice.delete(device);
  }

  statusElement.textContent =
    displayPower === null ? 'Нет данных' : displayPower ? 'Включен' : 'Выключен';
  statusElement.dataset.state = displayPower === null ? 'unknown' : displayPower ? 'on' : 'off';
  toggle.checked = displayPower === null ? false : displayPower;

  if (!isKnown) {
    hintElement.textContent = 'Нет свежего статуса питания. Проверьте последнее чтение с устройства.';
    return;
  }

  if (device === 'purifier') {
    const mode = Number(latest.purifier_mode?.value);
    const favoriteLevel = Number(latest.purifier_favorite_level?.value);
    const modeText = Number.isFinite(mode) ? purifierModeLabels[mode] || `Mode ${mode}` : 'режим неизвестен';
    const favoriteText = Number.isFinite(favoriteLevel)
      ? `Favorite level ${favoriteLevel}`
      : 'favorite level не прочитан';

    hintElement.textContent =
      `Обновлено в ${formatClock(powerRow.measured_at)}. Режим: ${modeText}, ${favoriteText}. ` +
      `PM2.5: ${formatValue(settings.purifier_pm25_low_threshold)}-${formatValue(settings.purifier_pm25_threshold)} ug/m3.`;
    return;
  }

  const humidifierMode = Number(latest.humidifier_mode?.value);
  const modeText = Number.isFinite(humidifierMode)
    ? humidifierModeLabels[humidifierMode] || `Mode ${humidifierMode}`
    : 'режим неизвестен';

  hintElement.textContent =
    `Обновлено в ${formatClock(powerRow.measured_at)}. Режим: ${modeText}. ` +
    `Диапазон ${formatValue(settings.humidifier_humidity_low_threshold)}-${formatValue(settings.humidifier_humidity_high_threshold)}%.`;
}

function commandLabel(command) {
  if (command === 'turn_on') return 'Включение';
  if (command === 'turn_off') return 'Выключение';
  if (command === 'set_fan_level') return 'Режим увлажнителя';
  if (command === 'set_favorite_level') return 'Скорость очистителя';
  return command;
}

function statusTone(status) {
  if (status === 'failed' || status === 'error') return 'danger';
  if (status === 'warning' || status === 'planned') return 'warning';
  if (status === 'sent' || status === 'info') return 'success';
  return 'neutral';
}

function updateEvents(events, commands) {
  const list = document.querySelector('#events');
  const items = [
    ...events.map((event) => ({
      device: event.device,
      title: event.message,
      time: event.created_at,
      tone: statusTone(event.severity),
      badge: event.severity,
    })),
    ...commands.map((command) => ({
      device: command.device,
      title: `${commandLabel(command.command)} · ${command.status}`,
      time: command.created_at,
      tone: statusTone(command.status),
      badge: command.status,
    })),
  ]
    .sort((a, b) => b.time.localeCompare(a.time))
    .slice(0, 12);

  list.innerHTML = '';

  if (items.length === 0) {
    const empty = document.createElement('li');
    empty.className = 'feed-empty';
    empty.textContent = 'Журнал пока пуст. После первого опроса и первых команд записи появятся здесь.';
    list.append(empty);
    return;
  }

  items.forEach((item) => {
    const li = document.createElement('li');
    li.className = 'feed-item';

    const head = document.createElement('div');
    head.className = 'feed-head';

    const titleWrap = document.createElement('div');
    titleWrap.className = 'feed-title-wrap';

    const badge = document.createElement('span');
    badge.className = 'feed-badge';
    badge.dataset.tone = item.tone;
    badge.textContent = item.badge;

    const title = document.createElement('strong');
    title.textContent = `${deviceLabels[item.device] || item.device}: ${item.title}`;

    titleWrap.append(badge, title);

    const time = document.createElement('time');
    time.textContent = formatDateTime(item.time);

    head.append(titleWrap, time);
    li.append(head);
    list.append(li);
  });
}

function computeYAxisRange(metric, data, settings) {
  if (metric === 'humidity') {
    const thresholds = thresholdsFor(metric, settings).map((item) => Number(item.value)).filter(Number.isFinite);
    const values = [...data, ...thresholds].filter(Number.isFinite);
    const min = Math.max(0, Math.min(...values, 0) - 5);
    const max = Math.min(100, Math.max(...values, 100) + 5);
    return { min, max };
  }

  if (metric === 'pm25') {
    const thresholds = thresholdsFor(metric, settings).map((item) => Number(item.value)).filter(Number.isFinite);
    const values = [...data, ...thresholds].filter(Number.isFinite);
    if (!values.length) return {};
    const min = Math.max(0, Math.min(...values, 0) - 5);
    const max = Math.max(...values, 25) + 5;
    return { min, max };
  }

  return {};
}

function renderLineChart(metric, history, settings) {
  const config = chartConfig[metric];
  const chart = getChart(config.element);
  const points = history.filter((row) => row.metric === metric);
  const labels = points.map((row) => formatClock(row.measured_at));
  const data = points.map((row) => Number(row.value));
  const yAxisRange = computeYAxisRange(metric, data, settings);
  const markLines = thresholdsFor(metric, settings)
    .filter((item) => Number.isFinite(item.value))
    .map((item) => ({
      yAxis: item.value,
      name: item.label,
      lineStyle: { color: item.color, type: 'dashed', width: 2 },
      label: {
        formatter: `${item.label}: ${formatValue(item.value)}`,
        color: item.color,
        backgroundColor: '#ffffff',
        padding: [2, 6],
        borderRadius: 999,
      },
    }));

  chart.setOption(
    {
      color: [config.color],
      animationDuration: 0,
      animationDurationUpdate: 0,
      animationEasingUpdate: 'linear',
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#0f172a',
        borderWidth: 0,
        textStyle: { color: '#f8fafc' },
        valueFormatter: (value) => `${formatValue(value)} ${config.unit}`,
      },
      grid: { left: 48, right: 20, top: 18, bottom: 34 },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: labels,
        axisLabel: { color: '#8a94a6', hideOverlap: true },
        axisLine: { lineStyle: { color: '#d7dfeb' } },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        name: config.unit,
        min: yAxisRange.min,
        max: yAxisRange.max,
        nameTextStyle: { color: '#8a94a6' },
        axisLabel: { color: '#8a94a6' },
        splitLine: { lineStyle: { color: '#edf2f8' } },
      },
      series: [
        {
          type: 'line',
          name: config.title,
          data,
          smooth: true,
          showSymbol: data.length <= 10,
          symbolSize: 7,
          lineStyle: { width: 3, color: config.color },
          itemStyle: { color: config.color },
          areaStyle: { opacity: 0.12, color: config.color },
          markLine: { symbol: 'none', animation: false, data: markLines },
        },
      ],
    },
    true
  );
}

function renderCharts(history, settings) {
  Object.keys(chartConfig).forEach((metric) => renderLineChart(metric, history, settings));
}

function scheduleRefresh(seconds = dashboardRefreshSeconds) {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    loadSnapshot().catch((error) => {
      setStatus(`Ошибка автообновления: ${error.message || error}`, 'danger');
    });
  }, Math.max(1, Number(seconds)) * 1000);
}

function setPollLoading(isLoading) {
  pollNowButton.disabled = isLoading;
  pollNowButton.classList.toggle('is-loading', isLoading);
}

async function requestPoll() {
  const response = await fetch('/api/poll', { method: 'POST' });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || 'не удалось обновить данные');
  }
}

async function patchJson(url, payload) {
  const response = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || 'запрос не выполнен');
  }
  return response.json();
}

async function loadSnapshot() {
  const response = await fetch('/api/snapshot');
  if (!response.ok) throw new Error('snapshot недоступен');

  latestSnapshot = await response.json();
  const latest = latestByMetric(latestSnapshot.latest);

  updateOverview(latestSnapshot.latest, latestSnapshot.settings);
  updatePresetButtons(dashboardRefreshSeconds);
  updateDeviceInputs(latestSnapshot.settings, latest);
  updateDeviceStatus('purifier', latest, latestSnapshot.settings);
  updateDeviceStatus('humidifier', latest, latestSnapshot.settings);
  updateEvents(latestSnapshot.events, latestSnapshot.commands);
  renderCharts(latestSnapshot.history, latestSnapshot.settings);
  setStatus(`Данные обновлены в ${new Date().toLocaleTimeString('ru-RU')}`, 'success');
}

async function applyPurifierSettings() {
  if (!latestSnapshot) return;

  applyPurifierSettingsButton.disabled = true;
  setStatus('Применяем настройки очистителя...', 'warning');

  const settingsPayload = {
    purifier_pm25_low_threshold: Number(purifierPm25LowThresholdInput.value),
    purifier_pm25_threshold: Number(purifierPm25ThresholdInput.value),
    purifier_auto_on_pm25_enabled: purifierAutoOnPm25EnabledInput.checked,
    purifier_auto_off_pm25_enabled: purifierAutoOffPm25EnabledInput.checked,
  };

  try {
    await patchJson('/api/settings', settingsPayload);
    await patchJson('/api/devices/purifier/favorite-level', { level: Number(purifierFavoriteLevelInput.value) });

    let pollError = null;
    try {
      await requestPoll();
    } catch (error) {
      pollError = error;
    }

    clearDirtyFields(purifierFieldIds);
    await loadSnapshot();
    setStatus(
      pollError
        ? `Настройки очистителя сохранены, но опрос не удался: ${pollError.message || pollError}`
        : 'Настройки очистителя применены',
      pollError ? 'warning' : 'success'
    );
  } catch (error) {
    await loadSnapshot().catch(() => {});
    setStatus(`Ошибка настроек очистителя: ${error.message || error}`, 'danger');
  } finally {
    applyPurifierSettingsButton.disabled = false;
  }
}

async function applyHumidifierSettings() {
  if (!latestSnapshot) return;

  applyHumidifierSettingsButton.disabled = true;
  setStatus('Применяем настройки увлажнителя...', 'warning');

  const settingsPayload = {
    humidifier_humidity_high_threshold: Number(humidifierHumidityHighThresholdInput.value),
    humidifier_humidity_low_threshold: Number(humidifierHumidityLowThresholdInput.value),
    humidifier_auto_on_low_humidity_enabled: humidifierAutoOnLowHumidityEnabledInput.checked,
    humidifier_auto_off_high_humidity_enabled: humidifierAutoOffHighHumidityEnabledInput.checked,
  };

  try {
    await patchJson('/api/settings', settingsPayload);
    await patchJson('/api/devices/humidifier/fan-level', { level: Number(humidifierFanLevelSelect.value) });

    let pollError = null;
    try {
      await requestPoll();
    } catch (error) {
      pollError = error;
    }

    clearDirtyFields(humidifierFieldIds);
    await loadSnapshot();
    setStatus(
      pollError
        ? `Настройки увлажнителя сохранены, но опрос не удался: ${pollError.message || pollError}`
        : 'Настройки увлажнителя применены',
      pollError ? 'warning' : 'success'
    );
  } catch (error) {
    await loadSnapshot().catch(() => {});
    setStatus(`Ошибка настроек увлажнителя: ${error.message || error}`, 'danger');
  } finally {
    applyHumidifierSettingsButton.disabled = false;
  }
}

function bindDirtyTracking() {
  [
    purifierPm25LowThresholdInput,
    purifierPm25ThresholdInput,
    purifierAutoOnPm25EnabledInput,
    purifierAutoOffPm25EnabledInput,
    purifierFavoriteLevelInput,
    humidifierHumidityLowThresholdInput,
    humidifierHumidityHighThresholdInput,
    humidifierAutoOnLowHumidityEnabledInput,
    humidifierAutoOffHighHumidityEnabledInput,
    humidifierFanLevelSelect,
  ].forEach((element) => {
    element.addEventListener(element.type === 'checkbox' || element.tagName === 'SELECT' ? 'change' : 'input', markDirty);
  });
}

pollNowButton.addEventListener('click', async () => {
  setPollLoading(true);
  setStatus('Запрашиваем свежие показания...', 'warning');
  try {
    await requestPoll();
    await loadSnapshot();
  } catch (error) {
    await loadSnapshot().catch(() => {});
    setStatus(`Ошибка обновления: ${error.message || error}`, 'danger');
  } finally {
    setPollLoading(false);
  }
});

presetButtons.forEach((button) => {
  button.addEventListener('click', () => {
    dashboardRefreshSeconds = Number(button.dataset.seconds);
    updatePresetButtons(dashboardRefreshSeconds);
    document.querySelector('#pollIntervalDisplay').textContent = `${dashboardRefreshSeconds} сек`;
    scheduleRefresh(dashboardRefreshSeconds);
    setStatus(`Автообновление переключено на ${dashboardRefreshSeconds} сек`, 'success');
  });
});

[purifierPowerToggle, humidifierPowerToggle].forEach((toggle) => {
  toggle.addEventListener('change', async () => {
    const device = toggle.dataset.device;
    const previous = !toggle.checked;
    pendingPowerByDevice.set(device, toggle.checked);
    toggle.disabled = true;
    setStatus('Отправляем команду устройству...', 'warning');
    try {
      await patchJson(`/api/devices/${device}/power`, { power: toggle.checked });
      await loadSnapshot();
    } catch (error) {
      pendingPowerByDevice.delete(device);
      toggle.checked = previous;
      setStatus(`Ошибка команды: ${error.message || error}`, 'danger');
    } finally {
      toggle.disabled = false;
    }
  });
});

applyPurifierSettingsButton.addEventListener('click', applyPurifierSettings);
applyHumidifierSettingsButton.addEventListener('click', applyHumidifierSettings);

window.addEventListener('resize', () => {
  charts.forEach((chart) => chart.resize());
});

bindDirtyTracking();
scheduleRefresh(dashboardRefreshSeconds);
loadSnapshot().catch((error) => {
  setStatus(`Ошибка dashboard: ${error.message || error}`, 'danger');
});
