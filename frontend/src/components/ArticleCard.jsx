import React, { useState, useRef } from 'react'

function ArticleCard({ article, onDismiss, onSave, isSaved, viewMode = 'cards' }) {
  const { title, url, source, author, read_time, topics, summary } = article
  
  // Swipe state for single view
  const [swipeX, setSwipeX] = useState(0)
  const [swiping, setSwiping] = useState(false)
  const touchStartX = useRef(0)
  const touchStartY = useRef(0)
  const cardRef = useRef(null)

  // Haptic feedback (if supported)
  const vibrate = (pattern = 10) => {
    if (navigator.vibrate) {
      navigator.vibrate(pattern)
    }
  }

  // Swipe handlers for single view
  const handleTouchStart = (e) => {
    touchStartX.current = e.touches[0].clientX
    touchStartY.current = e.touches[0].clientY
    setSwiping(true)
  }

  const handleTouchMove = (e) => {
    if (!swiping) return
    
    const deltaX = e.touches[0].clientX - touchStartX.current
    const deltaY = e.touches[0].clientY - touchStartY.current
    
    // Only swipe horizontally if movement is more horizontal than vertical
    if (Math.abs(deltaX) > Math.abs(deltaY)) {
      e.preventDefault()
      setSwipeX(deltaX)
    }
  }

  const handleTouchEnd = () => {
    if (Math.abs(swipeX) > 100) {
      // Swipe threshold reached
      if (swipeX > 0) {
        // Swipe right = Save
        vibrate(15)
        onSave(article)
      } else {
        // Swipe left = Dismiss
        vibrate([10, 50, 10])
        onDismiss(article.id)
      }
    }
    setSwipeX(0)
    setSwiping(false)
  }

  // Single view - larger, centered card with swipe
  if (viewMode === 'single') {
    const swipeOpacity = Math.min(Math.abs(swipeX) / 100, 1)
    const isSwipingRight = swipeX > 0
    const isSwipingLeft = swipeX < 0

    return (
      <div className="relative">
        {/* Swipe indicators */}
        <div className={`absolute inset-0 flex items-center justify-start pl-8 transition-opacity ${isSwipingLeft ? 'opacity-100' : 'opacity-0'}`}>
          <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center" style={{ opacity: swipeOpacity }}>
            <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
        </div>
        <div className={`absolute inset-0 flex items-center justify-end pr-8 transition-opacity ${isSwipingRight ? 'opacity-100' : 'opacity-0'}`}>
          <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center" style={{ opacity: swipeOpacity }}>
            <svg className="w-8 h-8 text-green-500" fill={swipeOpacity > 0.5 ? "currentColor" : "none"} stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
            </svg>
          </div>
        </div>

        {/* Card - clickable */}
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          ref={cardRef}
          className="block bg-white rounded-2xl shadow-sm border border-gray-100 p-4 sm:p-8 max-w-2xl mx-auto transition-transform relative z-10 hover:shadow-md"
          style={{ 
            transform: `translateX(${swipeX}px) rotate(${swipeX * 0.03}deg)`,
            transition: swiping ? 'none' : 'transform 0.3s ease-out'
          }}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          onClick={(e) => {
            // Prevent navigation if swiping
            if (Math.abs(swipeX) > 10) {
              e.preventDefault()
            }
          }}
        >
          {/* Source & Dismiss */}
          <div className="flex items-center justify-between mb-3 sm:mb-4">
            <span className="text-xs sm:text-sm font-medium text-gray-500">{source}</span>
            <button
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); vibrate(); onDismiss(article.id) }}
              className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              title="Don't show again"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Title */}
          <h2 className="text-xl sm:text-2xl font-bold text-gray-900 mb-2 sm:mb-3 leading-tight group-hover:text-orange-600">
            {title}
          </h2>

          {/* Summary */}
          <p className="text-sm sm:text-base text-gray-600 mb-4 sm:mb-5 leading-relaxed">
            {summary}
          </p>

          {/* Topics */}
          <div className="flex flex-wrap gap-1.5 sm:gap-2 mb-4 sm:mb-5">
            {topics.slice(0, 4).map((topic) => (
              <span
                key={topic}
                className="px-2 sm:px-3 py-0.5 sm:py-1 text-xs sm:text-sm font-medium text-gray-600 bg-gray-100 rounded-full"
              >
                {topic}
              </span>
            ))}
          </div>

          {/* Meta */}
          <div className="flex items-center gap-2 sm:gap-3 text-xs sm:text-sm text-gray-500">
            {author && author !== source && (
              <>
                <span>{author}</span>
                <span>·</span>
              </>
            )}
            <div className="flex items-center gap-1">
              <svg className="w-3.5 h-3.5 sm:w-4 sm:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{read_time} min</span>
            </div>
          </div>
        </a>

        {/* Mobile Bottom Action Bar - fixed at bottom, equal size buttons */}
        <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 px-3 py-2 flex gap-2 sm:hidden z-50 safe-bottom">
          <button
            onClick={() => { vibrate([10, 50, 10]); onDismiss(article.id) }}
            className="flex-1 flex items-center justify-center gap-1.5 py-2.5 bg-gray-100 text-gray-700 text-sm font-medium rounded-xl active:scale-95 transition-transform"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
            Skip
          </button>
          <button
            onClick={() => { vibrate(15); onSave(article) }}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-sm font-medium rounded-xl active:scale-95 transition-transform ${
              isSaved 
                ? 'bg-gray-900 text-white' 
                : 'bg-gray-100 text-gray-700'
            }`}
          >
            <svg className="w-4 h-4" fill={isSaved ? "currentColor" : "none"} stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
            </svg>
            {isSaved ? 'Saved' : 'Save'}
          </button>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 flex items-center justify-center gap-1.5 py-2.5 bg-orange-500 text-white text-sm font-medium rounded-xl active:scale-95 transition-transform"
          >
            Read
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          </a>
        </div>

        {/* Desktop Actions */}
        <div className="hidden sm:flex gap-3 max-w-2xl mx-auto mt-4">
          <button
            onClick={() => { vibrate(); onSave(article) }}
            className={`flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg font-medium transition-colors ${
              isSaved 
                ? 'bg-gray-900 text-white' 
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            <svg className="w-5 h-5" fill={isSaved ? "currentColor" : "none"} stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
            </svg>
            {isSaved ? 'Saved' : 'Save'}
          </button>
          <button
            onClick={() => { vibrate(); onDismiss(article.id) }}
            className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg font-medium bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
            Skip
          </button>
        </div>
        
        {/* Spacer for bottom bar on mobile */}
        <div className="h-16 sm:hidden"></div>
      </div>
    )
  }

  // Cards view - compact grid card
  return (
    <div className="article-card bg-white rounded-xl shadow-sm border border-gray-100 p-3 sm:p-5 flex flex-col h-full hover:shadow-md transition-shadow">
      {/* Source & Dismiss */}
      <div className="flex items-center justify-between mb-2 sm:mb-3">
        <span className="text-xs sm:text-sm font-medium text-gray-500 truncate">{source}</span>
        <button
          onClick={() => onDismiss(article.id)}
          className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors flex-shrink-0"
          title="Don't show again"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Title */}
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="group"
      >
        <h2 className="text-sm sm:text-lg font-semibold text-gray-900 group-hover:text-orange-600 transition-colors mb-2 line-clamp-2 leading-snug">
          {title}
        </h2>
      </a>

      {/* Summary - hidden on very small screens */}
      <p className="hidden xs:block text-xs sm:text-sm text-gray-600 mb-3 sm:mb-4 line-clamp-2 sm:line-clamp-3 flex-grow leading-relaxed">
        {summary}
      </p>

      {/* Topics - show fewer on mobile */}
      <div className="flex flex-wrap gap-1 sm:gap-1.5 mb-3 sm:mb-4">
        {topics.slice(0, 2).map((topic) => (
          <span
            key={topic}
            className="px-1.5 sm:px-2 py-0.5 text-xs font-medium text-gray-500 bg-gray-100 rounded-full"
          >
            {topic}
          </span>
        ))}
      </div>

      {/* Meta */}
      <div className="flex items-center text-xs sm:text-sm text-gray-500 mb-3 sm:mb-4 pt-2 sm:pt-3 border-t border-gray-100">
        <div className="flex items-center gap-1">
          <svg className="w-3 h-3 sm:w-4 sm:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{read_time} min</span>
        </div>
      </div>

      {/* Actions - balanced icon buttons with external link */}
      <div className="flex items-center gap-2 mt-auto">
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onSave(article) }}
          className={`flex items-center justify-center p-2 rounded-lg transition-colors ${
            isSaved 
              ? 'bg-gray-900 text-white' 
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
          title={isSaved ? 'Saved' : 'Save'}
        >
          <svg className="w-4 h-4" fill={isSaved ? "currentColor" : "none"} stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
          </svg>
        </button>
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onDismiss(article.id) }}
          className="flex items-center justify-center p-2 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 transition-colors"
          title="Skip"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="flex items-center justify-center p-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors ml-auto"
          title="Read article"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </a>
      </div>
    </div>
  )
}

export default ArticleCard
