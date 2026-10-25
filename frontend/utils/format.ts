export function formatMoney(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || isNaN(amount)) return '0'
  return Math.round(amount).toLocaleString('ru-RU')
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  const parts = dateStr.split('-')
  if (parts.length === 3) {
    return `${parts[2]}.${parts[1]}.${parts[0]}`
  }
  return dateStr
}

export function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    const d = new Date(dateStr)
    return d.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return dateStr
  }
}

export function validateInnAndName(inn: string, legalForm: string, name: string): string | null {
  const cleanInn = String(inn || '').trim()
  if (!cleanInn) return 'ИНН обязателен для заполнения'
  if (!/^\d+$/.test(cleanInn)) return 'ИНН должен содержать только цифры'
  if (['ООО', 'АО'].includes(legalForm) && cleanInn.length !== 10) {
    return `ИНН юридического лица (${legalForm}) должен содержать ровно 10 цифр (введено: ${cleanInn.length})`
  }
  if (['ИП', 'Самозанятый'].includes(legalForm) && cleanInn.length !== 12) {
    return `ИНН для ${legalForm} должен содержать ровно 12 цифр (введено: ${cleanInn.length})`
  }
  if (!name || name.trim().length < 2) {
    return 'Название организации / ФИО должно содержать не менее 2 символов'
  }
  return null
}

export function validateCounterpartyInput(name: string, inn: string): string | null {
  const cleanName = String(name || '').trim()
  const cleanInn = String(inn || '').trim()

  if (!cleanName || cleanName.length < 2) {
    return 'Укажите наименование контрагента (не менее 2 символов)'
  }
  if (!cleanInn) {
    return 'Укажите ИНН контрагента (10 или 12 цифр)'
  }
  if (!/^\d+$/.test(cleanInn)) {
    return 'ИНН контрагента должен состоять только из цифр'
  }
  if (cleanInn.length !== 10 && cleanInn.length !== 12) {
    return `ИНН контрагента должен содержать ровно 10 (для ООО/АО) или 12 (для ИП) цифр (введено: ${cleanInn.length})`
  }
  return null
}
