"use client"

import {
  Stepper,
  StepperDescription,
  StepperIndicator,
  StepperItem,
  StepperSeparator,
  StepperTitle,
  StepperTrigger,
} from "@/components/ui/stepper"
import { CheckIcon, FileUpIcon, FileTextIcon, DatabaseIcon, ShieldCheckIcon, CheckCircle2Icon } from "lucide-react"
import { cn } from "@/lib/utils"

export type ProcessingStage =
  | "upload"
  | "ocr"
  | "brnet"
  | "validation"
  | "completed"

export interface ProcessingStepperProps {
  currentStage: ProcessingStage
  statusMessage?: string
  className?: string
}

const steps = [
  {
    step: 1,
    stage: "upload" as ProcessingStage,
    title: "Upload",
    description: "Documento recebido",
    icon: FileUpIcon,
  },
  {
    step: 2,
    stage: "ocr" as ProcessingStage,
    title: "OCR",
    description: "Extraindo texto do documento",
    icon: FileTextIcon,
  },
  {
    step: 3,
    stage: "brnet" as ProcessingStage,
    title: "Consulta BRNET",
    description: "Buscando exames obrigatórios",
    icon: DatabaseIcon,
  },
  {
    step: 4,
    stage: "validation" as ProcessingStage,
    title: "Validação",
    description: "Comparando exames",
    icon: ShieldCheckIcon,
  },
  {
    step: 5,
    stage: "completed" as ProcessingStage,
    title: "Concluído",
    description: "Processamento finalizado",
    icon: CheckCircle2Icon,
  },
]

export function ProcessingStepper({
  currentStage,
  statusMessage,
  className,
}: ProcessingStepperProps) {
  const currentStepIndex = steps.findIndex((s) => s.stage === currentStage)
  const currentStepNumber = currentStepIndex >= 0 ? currentStepIndex + 1 : 1

  return (
    <div className={cn("w-full max-w-2xl mx-auto", className)}>
      <Stepper value={currentStepNumber} orientation="vertical">
        {steps.map(({ step, stage, title, description, icon: Icon }) => {
          const isActive = stage === currentStage
          const isCompleted = step < currentStepNumber
          const isLoading = isActive && stage !== "completed"

          return (
            <StepperItem
              key={step}
              step={step}
              className="relative items-start not-last:flex-1 group"
              loading={isLoading}
            >
              <StepperTrigger className="items-start rounded pb-8 last:pb-0 cursor-default">
                <StepperIndicator className="mt-0.5">
                  {isCompleted ? (
                    <CheckIcon className="size-3" />
                  ) : isLoading ? null : (
                    <Icon className="size-3" />
                  )}
                </StepperIndicator>
                <div className="mt-0.5 space-y-1 px-3 text-left">
                  <StepperTitle className="text-base">{title}</StepperTitle>
                  <StepperDescription className="text-sm">
                    {isActive && statusMessage ? statusMessage : description}
                  </StepperDescription>
                </div>
              </StepperTrigger>
              {step < steps.length && (
                <StepperSeparator
                  className={cn(
                    "absolute inset-y-0 top-[calc(1.5rem+0.125rem)] left-3 -order-1 m-0 -translate-x-1/2",
                    "group-data-[orientation=horizontal]/stepper:w-[calc(100%-1.5rem-0.25rem)] group-data-[orientation=horizontal]/stepper:flex-none",
                    "group-data-[orientation=vertical]/stepper:h-[calc(100%-1.5rem-0.25rem)]"
                  )}
                />
              )}
            </StepperItem>
          )
        })}
      </Stepper>
    </div>
  )
}
