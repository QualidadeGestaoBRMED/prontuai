// Mock data generators for notifications and processes

import { Notification } from '@/types/notification'
import { ProcessNotification, ProcessResult } from '@/types/process'

// Generate mock notifications
export function generateMockNotifications(): Notification[] {
  const now = new Date()
  const notifications: Notification[] = []

  // Recent notification - Process completed (2 min ago)
  notifications.push({
    id: 'notif-1',
    type: 'process_completed',
    title: 'Processamento Concluído',
    message: '8 documentos aprovados, 2 pendentes de revisão',
    timestamp: new Date(now.getTime() - 2 * 60 * 1000),
    read: false,
    variant: 'warning',
    actionUrl: '/enviar-docs',
    actionLabel: 'Ver Resultados',
    metadata: {
      processId: 'process-123',
      batchId: 'batch-001',
      documentCount: 10,
    },
  })

  // Process started (10 min ago)
  notifications.push({
    id: 'notif-2',
    type: 'process_started',
    title: 'Processamento Iniciado',
    message: 'Iniciando processamento de 10 documentos',
    timestamp: new Date(now.getTime() - 10 * 60 * 1000),
    read: true,
    variant: 'default',
    metadata: {
      processId: 'process-123',
      batchId: 'batch-001',
      documentCount: 10,
    },
  })

  // Review approved (1 hour ago)
  notifications.push({
    id: 'notif-3',
    type: 'review_approved',
    title: 'Documento Aprovado',
    message: 'Seu documento foi aprovado na revisão',
    timestamp: new Date(now.getTime() - 60 * 60 * 1000),
    read: false,
    variant: 'success',
    actionUrl: '/enviar-docs',
    actionLabel: 'Ver Detalhes',
    metadata: {
      documentId: 'doc-456',
      cpf: '12345678901',
      reviewerEmail: 'maria@grupobrmed.com.br',
    },
  })

  // Process error (2 hours ago)
  notifications.push({
    id: 'notif-4',
    type: 'process_error',
    title: 'Erro no Processamento',
    message: 'Falha ao processar documento-invalido.pdf: formato não suportado',
    timestamp: new Date(now.getTime() - 2 * 60 * 60 * 1000),
    read: true,
    variant: 'error',
    metadata: {
      processId: 'process-122',
      batchId: 'batch-000',
    },
  })

  // Review rejected (3 hours ago)
  notifications.push({
    id: 'notif-5',
    type: 'review_rejected',
    title: 'Documento Rejeitado',
    message: 'Documento rejeitado: exames faltantes não correspondem',
    timestamp: new Date(now.getTime() - 3 * 60 * 60 * 1000),
    read: true,
    variant: 'error',
    actionUrl: '/enviar-docs',
    actionLabel: 'Ver Detalhes',
    metadata: {
      documentId: 'doc-455',
      cpf: '98765432100',
      reviewerEmail: 'joao@grupobrmed.com.br',
    },
  })

  // Process completed - all approved (Yesterday)
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  yesterday.setHours(14, 30, 0, 0)
  notifications.push({
    id: 'notif-6',
    type: 'process_completed',
    title: 'Processamento Concluído',
    message: 'Todos os 5 documentos foram aprovados!',
    timestamp: yesterday,
    read: true,
    variant: 'success',
    actionUrl: '/enviar-docs',
    actionLabel: 'Ver Resultados',
    metadata: {
      processId: 'process-121',
      batchId: 'batch-yesterday',
      documentCount: 5,
    },
  })

  // System message (2 days ago)
  const twoDaysAgo = new Date(now)
  twoDaysAgo.setDate(twoDaysAgo.getDate() - 2)
  twoDaysAgo.setHours(10, 0, 0, 0)
  notifications.push({
    id: 'notif-7',
    type: 'system_message',
    title: 'Atualização do Sistema',
    message: 'Nova funcionalidade: Central de Notificações disponível!',
    timestamp: twoDaysAgo,
    read: true,
    variant: 'default',
  })

  return notifications
}

// Generate mock active process
export function generateMockActiveProcess(): ProcessNotification {
  return {
    id: 'process-active-mock',
    batchId: 'batch-active-001',
    filename: 'lote-10-documentos.zip',
    documentCount: 10,
    status: 'processing',
    progress: 65,
    currentStep: 'validation',
    stepMessage: 'Validando exames...',
    startedAt: new Date(Date.now() - 3 * 60 * 1000), // 3 minutes ago
    documents: [
      { filename: 'prontuario-joao-silva.pdf', status: 'completed', progress: 100 },
      { filename: 'prontuario-maria-santos.pdf', status: 'completed', progress: 100 },
      { filename: 'prontuario-jose-oliveira.pdf', status: 'completed', progress: 100 },
      { filename: 'prontuario-ana-costa.pdf', status: 'processing', progress: 65 },
      { filename: 'prontuario-pedro-souza.pdf', status: 'pending', progress: 0 },
      { filename: 'prontuario-carla-lima.pdf', status: 'pending', progress: 0 },
      { filename: 'prontuario-bruno-alves.pdf', status: 'pending', progress: 0 },
      { filename: 'prontuario-julia-rocha.pdf', status: 'pending', progress: 0 },
      { filename: 'prontuario-lucas-martins.pdf', status: 'pending', progress: 0 },
      { filename: 'prontuario-fernanda-dias.pdf', status: 'pending', progress: 0 },
    ],
  }
}

// Generate mock process results
export function generateMockProcessResults(): ProcessResult[] {
  const now = new Date()
  const results: ProcessResult[] = []

  // Approved documents
  results.push({
    id: 'result-1',
    batchId: 'batch-001',
    filename: 'prontuario-joao-silva.pdf',
    cpf: '12345678901',
    patientName: 'João da Silva',
    uploadedAt: new Date(now.getTime() - 30 * 60 * 1000),
    processedAt: new Date(now.getTime() - 20 * 60 * 1000),
    status: 'approved',
    examesFaltantes: 0,
    examesExtras: 0,
    result: {
      cpf: '12345678901',
      patient_name: 'João da Silva',
      status: 'success',
      ocr_result: {
        text: 'Mock OCR text',
        exames_extraidos: ['Hemograma', 'Raio-X de Tórax'],
      },
      brmed_result: {
        exames_obrigatorios: ['Hemograma', 'Raio-X de Tórax'],
        empresa: 'BRMED',
      },
      validation_result: {
        exames_faltantes: [],
        exames_extras: [],
        analysis: 'Todos os exames obrigatórios foram encontrados.',
      },
    },
    submittedBy: 'usuario@grupobrmed.com.br',
  })

  // Rejected document
  results.push({
    id: 'result-2',
    batchId: 'batch-001',
    filename: 'prontuario-maria-santos.pdf',
    cpf: '98765432100',
    patientName: 'Maria Santos',
    uploadedAt: new Date(now.getTime() - 30 * 60 * 1000),
    processedAt: new Date(now.getTime() - 20 * 60 * 1000),
    status: 'rejected',
    rejectionReason: 'Exames obrigatórios faltantes',
    examesFaltantes: 2,
    examesExtras: 1,
    result: {
      cpf: '98765432100',
      patient_name: 'Maria Santos',
      status: 'partial',
      ocr_result: {
        text: 'Mock OCR text',
        exames_extraidos: ['Hemograma', 'Urina Tipo 1'],
      },
      brmed_result: {
        exames_obrigatorios: ['Hemograma', 'Raio-X de Tórax', 'Audiometria'],
        empresa: 'BRMED',
      },
      validation_result: {
        exames_faltantes: ['Raio-X de Tórax', 'Audiometria'],
        exames_extras: ['Urina Tipo 1'],
        analysis: 'Faltam 2 exames obrigatórios. Foi encontrado 1 exame adicional.',
      },
    },
    submittedBy: 'usuario@grupobrmed.com.br',
  })

  // Pending review
  results.push({
    id: 'result-3',
    batchId: 'batch-001',
    filename: 'prontuario-jose-oliveira.pdf',
    cpf: '11122233344',
    patientName: 'José Oliveira',
    uploadedAt: new Date(now.getTime() - 30 * 60 * 1000),
    processedAt: new Date(now.getTime() - 20 * 60 * 1000),
    status: 'pending_review',
    examesFaltantes: 1,
    examesExtras: 0,
    result: {
      cpf: '11122233344',
      patient_name: 'José Oliveira',
      status: 'partial',
      ocr_result: {
        text: 'Mock OCR text',
        exames_extraidos: ['Hemograma'],
      },
      brmed_result: {
        exames_obrigatorios: ['Hemograma', 'Raio-X de Tórax'],
        empresa: 'BRMED',
      },
      validation_result: {
        exames_faltantes: ['Raio-X de Tórax'],
        exames_extras: [],
        analysis: 'Falta 1 exame obrigatório.',
      },
    },
    submittedBy: 'usuario@grupobrmed.com.br',
  })

  // More approved documents from yesterday
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  yesterday.setHours(14, 0, 0, 0)

  for (let i = 0; i < 5; i++) {
    results.push({
      id: `result-yesterday-${i}`,
      batchId: 'batch-yesterday',
      filename: `documento-${i + 1}.pdf`,
      cpf: `${10000000000 + i}`,
      patientName: `Paciente ${i + 1}`,
      uploadedAt: new Date(yesterday.getTime() - 10 * 60 * 1000),
      processedAt: yesterday,
      status: 'approved',
      examesFaltantes: 0,
      examesExtras: 0,
      result: {
        cpf: `${10000000000 + i}`,
        patient_name: `Paciente ${i + 1}`,
        status: 'success',
        ocr_result: {
          text: 'Mock OCR text',
          exames_extraidos: ['Hemograma', 'Raio-X de Tórax'],
        },
        brmed_result: {
          exames_obrigatorios: ['Hemograma', 'Raio-X de Tórax'],
          empresa: 'BRMED',
        },
        validation_result: {
          exames_faltantes: [],
          exames_extras: [],
          analysis: 'Todos os exames obrigatórios foram encontrados.',
        },
      },
      submittedBy: 'usuario@grupobrmed.com.br',
    })
  }

  return results
}

// Simulate receiving a new notification after delay
export function simulateIncomingNotification(
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp'>) => void,
  delay: number = 5000
) {
  setTimeout(() => {
    addNotification({
      type: 'process_completed',
      title: 'Novo Processamento Concluído',
      message: '3 documentos processados com sucesso',
      read: false,
      variant: 'success',
      actionUrl: '/enviar-docs',
      actionLabel: 'Ver Resultados',
      metadata: {
        processId: `process-${Date.now()}`,
        batchId: `batch-${Date.now()}`,
        documentCount: 3,
      },
    })
  }, delay)
}
