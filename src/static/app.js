const metricIds = {
  pm25: 'pm25',
  temperature: 'temperature',
  humidity: 'humidity',
};

const gaugeConfig = {
  pm25: { element: 'pm25Gauge', min: 0, max: 120, color: '#ef4444', unit: 'ug/m3' },
  temperature: { element: 'temperatureGauge', min: 10, max: 35, color: '#f59e0b', unit: 'C' },
  humidity: { element: 'humidityGauge', min: 0, max: 100, color: '#06b6d4', unit: '%' },
};

const chartConfig = {
  pm25: { element: 'pm25Chart', title: 'PM2.5', unit: 'ug/m3', color: '#ef4444' },
  humidity: { element: 'humidityChart', title: 'Влажность', unit: '%', color: '#06b6d4' },
  temperature: { element: 'temperatureChart', title: 'Температура', unit: 'C', color: '#f59e0b' },
  purifier_motor_speed: { element: 'motorChart', title: 'Скорость очистителя', unit: 'rpm', color: '#22c55e' },
};

const statusEl = document.querySelector('#status');
const form = document.querySelector('#settingsForm');
const pollNowButton = document.querySelector('#pollNow');
const saveButton = form.querySelector('button[type="submit"]');
const charts = new Map();
let refreshTimer = null;
let currentSnapshot = null;

function formatValue(value) {
  if (value === undefined || value === null) return '--';
  return Number(value).toFixed(Number(value) % 1 === 0 ? 0 : 1);
}

function latestByMetric(rows) {
  return rows.reduce((acc, row) => {
    acc[row.metric] = row;
    return acc;
  }, {});
}

function getChart(elementId) {
  if (!window.echarts) {
    throw new Error('ECharts не загрузился. Проверь интернет или CDN.');
  }
  if (!charts.has(elementId)) {
    charts.set(elementId, echarts.init(document.getElementById(elementId), null, { renderer: 'canvas' }));
  }
  return charts.get(elementId);
}

function thresholdsFor(metric, settings) {
  if (metric === 'pm25') return [{ value: Number(settings.purifier_pm25_threshold), label: 'порог автоочистки' }];
  if (metric === 'humidity') {
    return [
      { value: Number(settings.humidifier_humidity_low_threshold), label: 'нижний порог' },
      { value: Number(settings.humidifier_humidity_high_threshold), label: 'верхний порог' },
    ];
  }
  return [];
}

function gaugeCaption(metric, settings) {
  if (metric === 'pm25') return `Шкала 0-120, порог автоочистки ${settings.purifier_pm25_threshold}`;
  if (metric === 'humidity') {
    return `Шкала 0-100, рабочий коридор ${settings.humidifier_humidity_low_threshold}-${settings.humidifier_humidity_high_threshold}%`;
  }
  return 'Шкала 10-35, без автоматического порога';
}

function renderGauge(metric, value, settings) {
  const config = gaugeConfig[metric];
  const chart = getChart(config.element);
  const numeric = Number(value);
  const safeValue = Number.isFinite(numeric) ? numeric : config.min;
  const thresholds = thresholdsFor(metric, settings);
  const axisStops = metric === 'humidity'
    ? [
      [Number(settings.humidifier_humidity_low_threshold) / 100, '#f97316'],
      [Number(settings.humidifier_humidity_high_threshold) / 100, '#06b6d4'],
      [1, '#f97316'],
    ]
    : metric === 'pm25'
      ? [[Number(settings.purifier_pm25_threshold) / config.max, '#22c55e'], [1, '#ef4444']]
      : [[1, config.color]];

  chart.setOption({
    animationDuration: 350,
    series: [
      {
        type: 'gauge',
        min: config.min,
        max: config.max,
        startAngle: 205,
        endAngle: -25,
        radius: '96%',
        center: ['50%', '60%'],
        progress: { show: true, width: 14, itemStyle: { color: config.color } },
        axisLine: { lineStyle: { width: 14, color: axisStops } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: {
          distance: -8,
          color: '#667085',
          fontSize: 11,
          formatter: (tick) => (tick === config.min || tick === config.max ? String(tick) : ''),
        },
        pointer: { width: 5, length: '58%', itemStyle: { color: '#172033' } },
        anchor: { show: true, size: 8, itemStyle: { color: '#172033' } },
        title: { show: false },
        detail: { show: false },
        data: [{ value: safeValue }],
      },
    ],
    graphic: thresholds.map((threshold, index) => ({
      type: 'text',
      left: index === 0 ? 12 : 'right',
      right: index === 0 ? undefined : 12,
      bottom: 4,
      style: {
        text: `${threshold.label}: ${formatValue(threshold.value)}`,
        fill: '#667085',
        fontSize: 11,
      },
    })),
  }, true);

  const caption = document.querySelector(`#${metric}GaugeCaption`);
  if (caption) caption.textContent = gaugeCaption(metric, settings);
}

function renderLineChart(metric, history, settings) {
  const config = chartConfig[metric];
  const chart = getChart(config.element);
  const points = history.filter((row) => row.metric === metric);
  const labels = points.map((row) => new Date(row.measured_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
  const data = points.map((row) => Number(row.value));
  const markLines = thresholdsFor(metric, settings)
    .filter((item) => Number.isFinite(item.value))
    .map((item) => ({
      yAxis: item.value,
      name: item.label,
      label: { formatter: `${item.label}: ${formatValue(item.value)}`, color: '#c2410c' },
      lineStyle: { color: '#f97316', type: 'dashed', width: 2 },
    }));

  chart.setOption({
    color: [config.color],
    animationDuration: 350,
    tooltip: {
      trigger: 'axis',
      valueFormatter: (val) => `${formatValue(val)} ${config.unit}`,
    },
    grid: { left: 54, right: 24, top: 26, bottom: 42 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: labels,
      axisLabel: { color: '#667085', hideOverlap: true },
      axisLine: { lineStyle: { color: '#c8d5e6' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: config.unit,
      nameTextStyle: { color: '#667085', align: 'left' },
      axisLabel: { color: '#667085' },
      splitLine: { lineStyle: { color: '#e5edf6' } },
    },
    series: [
      {
        name: config.title,
        type: 'line',
        smooth: true,
        showSymbol: data.length <= 12,
        symbolSize: 7,
        data,
        lineStyle: { width: 3, color: config.color },
        itemStyle: { color: config.color },
        areaStyle: { opacity: 0.14, color: config.color },
        markLine: {
          symbol: 'none',
          data: markLines,
        },
      },
    ],
  }, true);
}

function updateMetrics(rows, settings) {
  const latest = latestByMetric(rows);
  Object.entries(metricIds).forEach(([metric, id]) => {
    const value = latest[metric]?.value;
    document.querySelector(`#${id}`).textContent = formatValue(value);
    renderGauge(metric, value, settings);
  });
  updateDeviceStatus('purifier', latest.purifier_power);
  updateDeviceStatus('humidifier', latest.humidifier_power);
}

function updateDeviceStatus(device, row) {
  const statusElement = document.querySelector(`#${device}Status`);
  const hintEl = document.querySelector(`#${device}Hint`);
  const toggle = document.querySelector(`#${device}PowerToggle`);
  const isKnown = row?.value !== undefined && row?.value !== null;
  const isOn = Number(row?.value) === 1;

  statusElement.textContent = isKnown ? (isOn ? 'Включен' : 'Выключен') : '--';
  hintEl.textContent = isKnown && row.measured_at ? `Обновлено ${new Date(row.measured_at).toLocaleTimeString()}` : 'Нет данных';
  toggle.checked = isKnown && isOn;
}

function updateSettings(settings) {
  Object.entries(settings).forEach(([key, value]) => {
    const input = form.elements[key];
    if (!input) return;
    if (input.type === 'checkbox') {
      input.checked = Boolean(value);
    } else {
      input.value = value;
    }
  });
}

function updateEvents(events, commands) {
  const list = document.querySelector('#events');
  const items = [
    ...events.map((event) => ({ ...event, kind: 'event' })),
    ...commands.map((command) => ({
      device: command.device,
      message: `${command.command} (${command.status})`,
      created_at: command.created_at,
      kind: 'command',
    })),
  ].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 12);

  list.innerHTML = '';
  if (items.length === 0) {
    const empty = document.createElement('li');
    empty.textContent = 'Событий пока нет.';
    list.append(empty);
    return;
  }

  items.forEach((item) => {
    const li = document.createElement('li');
    const title = document.createElement('strong');
    title.textContent = `${item.device}: ${item.message}`;
    const time = document.createElement('time');
    time.textContent = new Date(item.created_at).toLocaleString();
    li.append(title, time);
    list.append(li);
  });
}

function renderCharts(history, settings) {
  Object.keys(chartConfig).forEach((metric) => renderLineChart(metric, history, settings));
}

function scheduleRefresh(seconds) {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(loadSnapshot, Math.max(1, Number(seconds)) * 1000);
}

function setPollLoading(isLoading) {
  pollNowButton.disabled = isLoading;
  pollNowButton.classList.toggle('is-loading', isLoading);
}

async function requestPoll() {
  const response = await fetch('/api/poll', { method: 'POST' });
  if (!response.ok) throw new Error('не удалось обновить данные');
}

async function loadSnapshot() {
  const response = await fetch('/api/snapshot');
  currentSnapshot = await response.json();
  updateMetrics(currentSnapshot.latest, currentSnapshot.settings);
  updateSettings(currentSnapshot.settings);
  updateEvents(currentSnapshot.events, currentSnapshot.commands);
  renderCharts(currentSnapshot.history, currentSnapshot.settings);
  scheduleRefresh(currentSnapshot.settings.poll_interval_seconds);
  statusEl.textContent = `Обновлено ${new Date().toLocaleTimeString()}`;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  const payload = {};
  ['poll_interval_seconds', 'command_cooldown_seconds', 'purifier_pm25_threshold', 'humidifier_humidity_high_threshold', 'humidifier_humidity_low_threshold'].forEach((key) => {
    payload[key] = Number(data.get(key));
  });
  payload.automations_enabled = form.elements.automations_enabled.checked;
  payload.control_enabled = form.elements.control_enabled.checked;

  saveButton.disabled = true;
  statusEl.textContent = 'Сохраняем настройки и обновляем данные...';
  try {
    const response = await fetch('/api/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error('не удалось сохранить настройки');
    await requestPoll();
    await loadSnapshot();
  } catch (error) {
    statusEl.textContent = `Ошибка сохранения: ${error}`;
  } finally {
    saveButton.disabled = false;
  }
});

pollNowButton.addEventListener('click', async () => {
  setPollLoading(true);
  statusEl.textContent = 'Обновляем показания...';
  try {
    await requestPoll();
    await loadSnapshot();
  } finally {
    setPollLoading(false);
  }
});

document.querySelectorAll('.power-switch input').forEach((toggle) => {
  toggle.addEventListener('change', async () => {
    const previous = !toggle.checked;
    toggle.disabled = true;
    statusEl.textContent = 'Отправляем команду устройству...';
    try {
      const response = await fetch(`/api/devices/${toggle.dataset.device}/power`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ power: toggle.checked }),
      });
      if (!response.ok) throw new Error('устройство не приняло команду');
      await loadSnapshot();
    } catch (error) {
      toggle.checked = previous;
      statusEl.textContent = `Ошибка команды: ${error}`;
    } finally {
      toggle.disabled = false;
    }
  });
});

window.addEventListener('resize', () => {
  charts.forEach((chart) => chart.resize());
});

loadSnapshot().catch((error) => {
  statusEl.textContent = `Ошибка dashboard: ${error}`;
});
