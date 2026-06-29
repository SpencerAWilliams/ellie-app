import React, { useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import ExamplesDetailedViewWeb from './components/ExamplesDetailedViewWeb'

const DESIGN_W = 1440
const DESIGN_H = 1024

function ScaleToFit({ children }) {
  const [scale, setScale] = useState(1)

  useEffect(() => {
    function update() {
      setScale(Math.min(
        window.innerWidth / DESIGN_W,
        window.innerHeight / DESIGN_H
      ))
    }
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  return (
    <div style={{
      width: '100vw',
      height: '100vh',
      overflow: 'hidden',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#e0e0e0',
    }}>
      <div style={{
        width: DESIGN_W,
        height: DESIGN_H,
        transform: `scale(${scale})`,
        transformOrigin: 'center center',
        flexShrink: 0,
      }}>
        {children}
      </div>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ScaleToFit>
      <ExamplesDetailedViewWeb />
    </ScaleToFit>
  </React.StrictMode>
)
