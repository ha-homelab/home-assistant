# select_devices.py

sensor_value = float(data.get('sensor_value', 0))
action = data.get('action')  # 'turn_on' или 'turn_off'
devices = data.get('devices', {})
tolerance = float(data.get('tolerance', 30))  # сейчас не используется, но оставлен на будущее

# Определим, положительное или отрицательное целевое значение
target_value = abs(sensor_value)

# Получаем кандидатов по их состоянию
candidates = []
for entity_id, wattage in devices.items():
    state = hass.states.get(entity_id)
    if not state:
        continue
    if action == 'turn_on' and state.state == 'off':
        candidates.append((entity_id, wattage))
    elif action == 'turn_off' and state.state == 'on':
        candidates.append((entity_id, wattage))

logger.info("Целевое значение (максимум): %.1f Вт", target_value)
logger.info("Действие: %s", action)
#logger.info("Кандидаты для %s: %s", action, [f"{e} ({w}W)" for e, w in candidates])

# Функция для генерации всех комбинаций
def all_combinations(entities):
    result = [[]]
    for ent in entities:
        result += [combo + [ent] for combo in result]
    return result

# Поиск наилучшей комбинации (максимальная мощность <= target_value, минимум устройств)
best_combo = []
best_sum = 0

for combo in all_combinations(candidates):
    if not combo:
        continue
    total = sum(item[1] for item in combo)
    if total <= target_value:
        if (total > best_sum or
            (total == best_sum and len(combo) < len(best_combo))):
            best_combo = combo
            best_sum = total
#    logger.info("Комбинация: %s → %s Вт", [item[0] for item in combo], total)

# Итог
entities = [item[0] for item in best_combo]
logger.info("Выбранные устройства: %s", entities)
logger.info("Суммарная мощность: %s Вт", best_sum)

output["entities"] = best_combo
output["total_watt"] = best_sum
