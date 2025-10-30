"use client"

import * as React from "react"
import { Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

type StepperContextValue = {
  currentStep: number
  orientation: "horizontal" | "vertical"
}

const StepperContext = React.createContext<StepperContextValue | undefined>(
  undefined
)

const useStepper = () => {
  const context = React.useContext(StepperContext)
  if (!context) {
    throw new Error("useStepper must be used within a Stepper")
  }
  return context
}

interface StepperProps extends React.HTMLAttributes<HTMLDivElement> {
  defaultValue?: number
  value?: number
  orientation?: "horizontal" | "vertical"
  children: React.ReactNode
}

const Stepper = React.forwardRef<HTMLDivElement, StepperProps>(
  (
    {
      defaultValue = 1,
      value: controlledValue,
      orientation = "horizontal",
      className,
      children,
      ...props
    },
    ref
  ) => {
    const [internalValue] = React.useState(defaultValue)
    const currentStep = controlledValue ?? internalValue

    return (
      <StepperContext.Provider value={{ currentStep, orientation }}>
        <div
          ref={ref}
          data-orientation={orientation}
          className={cn(
            "group/stepper flex",
            orientation === "horizontal" ? "flex-row items-center" : "flex-col",
            className
          )}
          {...props}
        >
          {children}
        </div>
      </StepperContext.Provider>
    )
  }
)
Stepper.displayName = "Stepper"

interface StepperItemProps extends React.HTMLAttributes<HTMLDivElement> {
  step: number
  loading?: boolean
  children: React.ReactNode
}

const StepperItem = React.forwardRef<HTMLDivElement, StepperItemProps>(
  ({ step, loading = false, className, children, ...props }, ref) => {
    const { currentStep, orientation } = useStepper()
    const isActive = currentStep === step
    const isCompleted = currentStep > step

    return (
      <div
        ref={ref}
        data-state={isActive ? "active" : isCompleted ? "completed" : "pending"}
        data-loading={loading || undefined}
        data-orientation={orientation}
        className={cn(
          "flex",
          orientation === "horizontal"
            ? "flex-row items-center"
            : "flex-col items-start",
          className
        )}
        {...props}
      >
        {children}
      </div>
    )
  }
)
StepperItem.displayName = "StepperItem"

interface StepperTriggerProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode
}

const StepperTrigger = React.forwardRef<
  HTMLButtonElement,
  StepperTriggerProps
>(({ className, children, ...props }, ref) => {
  const { orientation } = useStepper()

  return (
    <button
      ref={ref}
      type="button"
      className={cn(
        "flex items-center gap-2 text-left transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        "disabled:pointer-events-none disabled:opacity-50",
        orientation === "horizontal" ? "flex-row" : "flex-col items-start",
        className
      )}
      {...props}
    >
      {children}
    </button>
  )
})
StepperTrigger.displayName = "StepperTrigger"

interface StepperIndicatorProps extends React.HTMLAttributes<HTMLDivElement> {
  asChild?: boolean
  children?: React.ReactNode
}

const StepperIndicator = React.forwardRef<
  HTMLDivElement,
  StepperIndicatorProps
>(({ asChild = false, className, children, ...props }, ref) => {
  if (asChild) {
    return <>{children}</>
  }

  return (
    <div
      ref={ref}
      className={cn(
        "flex size-6 shrink-0 items-center justify-center rounded-full border-2 text-xs font-medium transition-colors",
        "group-data-[state=pending]:border-muted group-data-[state=pending]:bg-background group-data-[state=pending]:text-muted-foreground",
        "group-data-[state=active]:border-primary group-data-[state=active]:bg-primary group-data-[state=active]:text-primary-foreground",
        "group-data-[state=completed]:border-primary group-data-[state=completed]:bg-primary group-data-[state=completed]:text-primary-foreground",
        "group-data-[loading]:animate-pulse",
        className
      )}
      {...props}
    >
      {children || (
        <div className="flex items-center justify-center">
          <Loader2
            className="size-4 animate-spin"
            data-loading-icon
            aria-hidden="true"
          />
        </div>
      )}
    </div>
  )
})
StepperIndicator.displayName = "StepperIndicator"

const StepperSeparator = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => {
  const { orientation } = useStepper()

  return (
    <div
      ref={ref}
      aria-hidden="true"
      className={cn(
        "bg-border shrink-0 transition-colors",
        "group-data-[state=completed]:bg-primary",
        orientation === "horizontal"
          ? "h-[2px] w-full"
          : "w-[2px] h-full ml-3",
        className
      )}
      {...props}
    />
  )
})
StepperSeparator.displayName = "StepperSeparator"

interface StepperTitleProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
}

const StepperTitle = React.forwardRef<HTMLDivElement, StepperTitleProps>(
  ({ className, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "text-sm font-medium transition-colors",
          "group-data-[state=pending]:text-muted-foreground",
          "group-data-[state=active]:text-foreground",
          "group-data-[state=completed]:text-foreground",
          className
        )}
        {...props}
      >
        {children}
      </div>
    )
  }
)
StepperTitle.displayName = "StepperTitle"

interface StepperDescriptionProps
  extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
}

const StepperDescription = React.forwardRef<
  HTMLDivElement,
  StepperDescriptionProps
>(({ className, children, ...props }, ref) => {
  return (
    <div
      ref={ref}
      className={cn("text-xs text-muted-foreground", className)}
      {...props}
    >
      {children}
    </div>
  )
})
StepperDescription.displayName = "StepperDescription"

export {
  Stepper,
  StepperItem,
  StepperTrigger,
  StepperIndicator,
  StepperSeparator,
  StepperTitle,
  StepperDescription,
}
