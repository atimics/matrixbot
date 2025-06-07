'use client'

import { useState, useEffect, useRef } from 'react'
import { apiClient } from '@/lib/api'
import LoadingSpinner from '@/components/ui/LoadingSpinner'

interface Message {
  id: string
  type: 'ai' | 'user'
  content: string
  timestamp: Date
  isTyping?: boolean
}

interface SetupStep {
  key: string
  question: string
  type: 'text' | 'password' | 'select'
  options?: string[]
  validation?: string
  completed?: boolean
}

interface SetupWizardProps {
  onComplete: () => void
}

export default function SetupWizard({ onComplete }: SetupWizardProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [currentStep, setCurrentStep] = useState<SetupStep | null>(null)
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isTyping, setIsTyping] = useState(false)
  const [setupComplete, setSetupComplete] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    initializeSetup()
  }, [])

  const initializeSetup = async () => {
    setIsLoading(true)
    try {
      // Add welcome message
      const welcomeMessage: Message = {
        id: 'welcome',
        type: 'ai',
        content: 'Hello! I am Ratichat, your AI assistant. I need to gather some information to become fully operational. Let\'s begin the setup process.',
        timestamp: new Date()
      }
      setMessages([welcomeMessage])

      // Get first setup step
      const response = await apiClient.get('/api/setup/start')
      if (response.data.step) {
        setCurrentStep(response.data.step)
        await typeMessage(response.data.step.question)
      }
    } catch (error) {
      console.error('Failed to initialize setup:', error)
      await typeMessage('I encountered an error during initialization. Please refresh the page and try again.')
    } finally {
      setIsLoading(false)
    }
  }

  const typeMessage = async (content: string): Promise<void> => {
    return new Promise((resolve) => {
      setIsTyping(true)
      const messageId = `ai-${Date.now()}`
      
      // Add typing indicator
      const typingMessage: Message = {
        id: messageId,
        type: 'ai',
        content: '',
        timestamp: new Date(),
        isTyping: true
      }
      setMessages(prev => [...prev, typingMessage])

      // Simulate typing delay
      setTimeout(() => {
        setMessages(prev => prev.map(msg => 
          msg.id === messageId 
            ? { ...msg, content, isTyping: false }
            : msg
        ))
        setIsTyping(false)
        resolve()
      }, 1000 + Math.random() * 1000) // Random delay between 1-2 seconds
    })
  }

  const handleSubmit = async () => {
    if (!inputValue.trim() || !currentStep || isLoading) return

    setIsLoading(true)

    // Add user message
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      type: 'user',
      content: inputValue,
      timestamp: new Date()
    }
    setMessages(prev => [...prev, userMessage])

    try {
      const response = await apiClient.post('/api/setup/submit', {
        step_key: currentStep.key,
        value: inputValue
      })

      const { success, message, next_step, complete } = response.data

      if (success) {
        // Show success message
        await typeMessage(message || 'Perfect! Let me continue...')

        if (complete) {
          await typeMessage('Excellent! All necessary configurations are complete. I am now initializing my core systems. The dashboard will be available momentarily.')
          setSetupComplete(true)
          setTimeout(() => {
            onComplete()
          }, 2000)
        } else if (next_step) {
          setCurrentStep(next_step)
          await typeMessage(next_step.question)
        }
      } else {
        // Show error message and retry
        await typeMessage(message || 'That doesn\'t seem right. Please try again.')
      }
    } catch (error: any) {
      console.error('Setup submission error:', error)
      const errorMessage = error.response?.data?.detail || 'I encountered an error processing your input. Please try again.'
      await typeMessage(errorMessage)
    } finally {
      setInputValue('')
      setIsLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const getInputType = () => {
    if (!currentStep) return 'text'
    if (currentStep.type === 'password') return 'password'
    return 'text'
  }

  const getPlaceholder = () => {
    if (!currentStep) return 'Type your response...'
    if (currentStep.type === 'password') return 'Enter your password/key...'
    if (currentStep.type === 'select' && currentStep.options) {
      return `Choose: ${currentStep.options.join(', ')}`
    }
    return 'Type your response...'
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl bg-white rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 p-6 text-white">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center">
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
              </svg>
            </div>
            <div>
              <h1 className="text-2xl font-bold">Ratichat Setup</h1>
              <p className="text-blue-100">Conversational Configuration Assistant</p>
            </div>
          </div>
        </div>

        {/* Chat Messages */}
        <div className="h-96 overflow-y-auto p-6 space-y-4 bg-gray-50">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'} chat-message ${message.type}`}
            >
              <div
                className={`max-w-xs lg:max-w-md px-4 py-2 rounded-2xl ${
                  message.type === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-gray-800 shadow-sm border'
                }`}
              >
                {message.isTyping ? (
                  <div className="flex items-center space-x-1">
                    <LoadingSpinner size="small" color="gray" />
                    <span className="text-sm text-gray-500">Typing...</span>
                  </div>
                ) : (
                  <p className="text-sm">{message.content}</p>
                )}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        {!setupComplete && (
          <div className="p-6 bg-white border-t">
            <div className="flex space-x-3">
              <input
                type={getInputType()}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder={getPlaceholder()}
                disabled={isLoading || isTyping || !currentStep}
                className="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
              />
              <button
                onClick={handleSubmit}
                disabled={isLoading || isTyping || !inputValue.trim() || !currentStep}
                className="px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
              >
                {isLoading ? (
                  <LoadingSpinner size="small" color="white" />
                ) : (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                  </svg>
                )}
              </button>
            </div>
            
            {currentStep?.validation && (
              <p className="mt-2 text-xs text-gray-500">
                {currentStep.validation}
              </p>
            )}
          </div>
        )}

        {/* Setup Complete Status */}
        {setupComplete && (
          <div className="p-6 bg-green-50 border-t">
            <div className="flex items-center justify-center space-x-2 text-green-700">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
              </svg>
              <span className="font-medium">Setup Complete! Redirecting to dashboard...</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
