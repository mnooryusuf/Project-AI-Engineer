// src/components/Mascot.jsx
import React from 'react'

export default function Mascot({ className = '', size = 64 }) {
  return (
    <div className={`mascot-container relative flex items-center justify-center ${className}`} style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full mascot-float">
        <defs>
          <linearGradient id="aiGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="var(--accent-cyan)" />
            <stop offset="50%" stopColor="var(--accent-blue)" />
            <stop offset="100%" stopColor="var(--accent-purple)" />
          </linearGradient>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Outer Ring */}
        <circle cx="50" cy="50" r="45" stroke="url(#aiGradient)" strokeWidth="4" className="mascot-spin" strokeDasharray="70 30" opacity="0.8" strokeLinecap="round" />
        <circle cx="50" cy="50" r="38" stroke="url(#aiGradient)" strokeWidth="2" className="mascot-spin-reverse" strokeDasharray="30 20" opacity="0.5" strokeLinecap="round" />

        {/* Inner Core */}
        <circle cx="50" cy="50" r="28" fill="rgba(6, 182, 212, 0.15)" stroke="url(#aiGradient)" strokeWidth="2" filter="url(#glow)" />
        
        {/* Eyes */}
        <rect x="35" y="44" width="8" height="12" rx="4" fill="#fff" className="mascot-blink" filter="url(#glow)" />
        <rect x="57" y="44" width="8" height="12" rx="4" fill="#fff" className="mascot-blink" filter="url(#glow)" />
        
        {/* Antenna */}
        <line x1="50" y1="22" x2="50" y2="8" stroke="url(#aiGradient)" strokeWidth="4" strokeLinecap="round" />
        <circle cx="50" cy="8" r="4" fill="var(--accent-cyan)" filter="url(#glow)" className="mascot-pulse" />
      </svg>
    </div>
  )
}
