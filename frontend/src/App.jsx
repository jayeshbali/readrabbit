import React, { useState, useEffect, useCallback, useRef } from 'react'
import ArticleCard from './components/ArticleCard'
import AdminPage from './components/AdminPage'
import DiscoverAgent from './components/DiscoverAgent'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

function App() {
  const [articles, setArticles] = useState([])
  const [savedArticles, setSavedArticles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [shuffling, setShuffling] = useState(false)
  const [serverWaking, setServerWaking] = useState(false)
  
  // UI State
  const [activeTab, setActiveTab] = useState('discover') // 'discover' | 'saved'
  const [viewMode, setViewMode] = useState('feed') // 'feed' | 'single'
  const [singleIndex, setSingleIndex] = useState(0) // For single view navigation
  const [showAdmin, setShowAdmin] = useState(false) // Admin page toggle
  const [showAgent, setShowAgent] = useState(false) // Discovery agent toggle
  
  // Toast notification state
  const [toast, setToast] = useState(null)
  
  // Pull to refresh state
  const [pullDistance, setPullDistance] = useState(0)
  const [isPulling, setIsPulling] = useState(false)
  const mainRef = useRef(null)
  const touchStartY = useRef(0)
  
  // Track load time for "waking up" message
  const loadStartTime = useRef(Date.now())

  // Show toast notification
  const showToast = (message, type = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 2500)
  }

  // Load saved articles from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('readrabbit_saved')
    if (saved) {
      setSavedArticles(JSON.parse(saved))
    }
  }, [])

  // Save to localStorage when savedArticles changes
  useEffect(() => {
    localStorage.setItem('readrabbit_saved', JSON.stringify(savedArticles))
  }, [savedArticles])

  // Show "waking up" message if loading takes > 3 seconds
  useEffect(() => {
    if (loading) {
      const timer = setTimeout(() => {
        setServerWaking(true)
      }, 3000)
      return () => clearTimeout(timer)
    } else {
      setServerWaking(false)
    }
  }, [loading])

  const fetchArticles = useCallback(async (append = false) => {
    try {
      setShuffling(true)
      loadStartTime.current = Date.now()
      const count = viewMode === 'single' ? 1 : 4

      // Use recommendations if user has saved articles, otherwise random
      const savedIds = JSON.parse(localStorage.getItem('readrabbit_saved') || '[]')
      let fetchedArticles = []

      if (savedIds.length > 0) {
        const response = await fetch(`${API_BASE}/recommendations?count=${count}`)
        if (!response.ok) throw new Error('Failed to fetch recommendations')
        const data = await response.json()
        fetchedArticles = data.recommendations || []
      }

      // Fall back to random if no recommendations returned
      if (fetchedArticles.length === 0) {
        const response = await fetch(`${API_BASE}/articles/random?count=${count}`)
        if (!response.ok) throw new Error('Failed to fetch articles')
        const data = await response.json()
        fetchedArticles = data.articles || []
      }

      if (append && viewMode === 'feed') {
        setArticles(prev => [...prev, ...fetchedArticles])
      } else {
        setArticles(fetchedArticles)
      }
      
      setSingleIndex(0)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
      setShuffling(false)
      setPullDistance(0)
      setIsPulling(false)
    }
  }, [viewMode])

  useEffect(() => {
    fetchArticles()
  }, [fetchArticles])

  // Pull to refresh handlers
  const handleTouchStart = (e) => {
    if (mainRef.current?.scrollTop === 0) {
      touchStartY.current = e.touches[0].clientY
    }
  }

  const handleTouchMove = (e) => {
    if (mainRef.current?.scrollTop === 0 && touchStartY.current > 0) {
      const distance = e.touches[0].clientY - touchStartY.current
      if (distance > 0 && distance < 150) {
        setPullDistance(distance)
        setIsPulling(true)
      }
    }
  }

  const handleTouchEnd = () => {
    if (pullDistance > 80) {
      fetchArticles()
      showToast('Refreshing...', 'info')
    }
    setPullDistance(0)
    setIsPulling(false)
    touchStartY.current = 0
  }

  const handleDismiss = async (articleId) => {
    try {
      await fetch(`${API_BASE}/articles/${articleId}/dismiss`, { method: 'POST' })
      
      if (viewMode === 'single') {
        const response = await fetch(`${API_BASE}/articles/random?count=1`)
        const data = await response.json()
        if (data.articles.length > 0) {
          setArticles(data.articles)
        }
      } else {
        const response = await fetch(`${API_BASE}/articles/random?count=1`)
        const data = await response.json()
        if (data.articles.length > 0) {
          setArticles((prev) =>
            prev.map((a) => (a.id === articleId ? data.articles[0] : a))
          )
        }
      }
      showToast('Article dismissed')
    } catch (err) {
      console.error('Failed to dismiss article:', err)
    }
  }

  const handleSave = (article) => {
    const isAlreadySaved = savedArticles.some((a) => a.id === article.id)
    if (isAlreadySaved) {
      setSavedArticles((prev) => prev.filter((a) => a.id !== article.id))
      showToast('Removed from saved')
    } else {
      setSavedArticles((prev) => [...prev, article])
      showToast('Saved for later! 🐰')
    }
    // Tell backend so recommendation engine can learn your interests
    fetch(`${API_BASE}/articles/${article.id}/save`, { method: 'POST' }).catch(() => {})
  }

  const isArticleSaved = (articleId) => {
    return savedArticles.some((a) => a.id === articleId)
  }

  const handleShowMore = () => {
    if (viewMode === 'single' && singleIndex < articles.length - 1) {
      setSingleIndex((prev) => prev + 1)
    } else if (viewMode === 'feed') {
      // Append 4 more articles
      fetchArticles(true)
    } else {
      fetchArticles()
    }
  }

  // View mode icons - Feed (default) and Single
  const ViewToggle = () => (
    <div className="flex items-center bg-gray-100 rounded-lg p-1">
      {/* Feed - default */}
      <button
        onClick={() => setViewMode('feed')}
        className={`flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-200 ${
          viewMode === 'feed' ? 'bg-white text-gray-900 shadow-sm scale-105' : 'text-gray-600 hover:text-gray-900'
        }`}
        title="Feed"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
        </svg>
        <span className="hidden sm:inline">Feed</span>
      </button>
      {/* Single */}
      <button
        onClick={() => setViewMode('single')}
        className={`flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-200 ${
          viewMode === 'single' ? 'bg-white text-gray-900 shadow-sm scale-105' : 'text-gray-600 hover:text-gray-900'
        }`}
        title="Single"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v14a1 1 0 01-1 1H5a1 1 0 01-1-1V5z" />
        </svg>
        <span className="hidden sm:inline">Single</span>
      </button>
    </div>
  )

  // Skeleton card for loading state
  const SkeletonCard = () => (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-3 sm:p-5 animate-pulse">
      <div className="flex items-center justify-between mb-3">
        <div className="h-3 w-20 bg-gray-200 rounded"></div>
        <div className="h-4 w-4 bg-gray-200 rounded"></div>
      </div>
      <div className="h-5 w-full bg-gray-200 rounded mb-2"></div>
      <div className="h-5 w-3/4 bg-gray-200 rounded mb-4"></div>
      <div className="h-3 w-full bg-gray-100 rounded mb-2"></div>
      <div className="h-3 w-2/3 bg-gray-100 rounded mb-4"></div>
      <div className="flex gap-1.5 mb-4">
        <div className="h-5 w-14 bg-gray-100 rounded-full"></div>
        <div className="h-5 w-16 bg-gray-100 rounded-full"></div>
      </div>
      <div className="flex gap-2 pt-3 border-t border-gray-100">
        <div className="h-8 w-8 bg-gray-200 rounded-lg"></div>
        <div className="h-8 flex-1 bg-gray-200 rounded-lg"></div>
      </div>
    </div>
  )

  // Loading state with skeleton
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        {/* Header skeleton */}
        <header className="bg-white border-b border-gray-200">
          <div className="max-w-6xl mx-auto px-3 sm:px-4 py-3 sm:py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-9 h-9 sm:w-10 sm:h-10 bg-orange-100 rounded-xl flex items-center justify-center animate-bounce">
                  <span className="text-xl sm:text-2xl">🐰</span>
                </div>
                <div className="h-6 w-24 bg-gray-200 rounded hidden sm:block"></div>
              </div>
              <div className="flex items-center gap-2">
                <div className="h-8 w-20 bg-gray-100 rounded-lg"></div>
                <div className="h-8 w-8 bg-gray-100 rounded-lg"></div>
              </div>
            </div>
          </div>
        </header>
        
        {/* Tabs skeleton */}
        <div className="bg-white border-b border-gray-100">
          <div className="max-w-6xl mx-auto px-3 sm:px-4 py-2 sm:py-3">
            <div className="flex justify-center">
              <div className="h-10 w-48 bg-gray-100 rounded-full"></div>
            </div>
          </div>
        </div>

        {/* Content skeleton */}
        <main className="max-w-6xl mx-auto px-3 sm:px-4 py-4 sm:py-8">
          {/* Waking up message */}
          {serverWaking && (
            <div className="text-center mb-6 animate-fade-in">
              <p className="text-sm text-gray-500">
                <span className="inline-block animate-pulse">☕</span> Waking up server... This may take up to 30 seconds
              </p>
            </div>
          )}
          
          <div className="max-w-2xl mx-auto space-y-4">
            {[1, 2, 3, 4].map((i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        </main>
      </div>
    )
  }

  // Error state with better styling
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="text-center max-w-sm">
          <div className="w-16 h-16 bg-red-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <span className="text-3xl">😵</span>
          </div>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Oops! Something went wrong</h2>
          <p className="text-gray-500 mb-6 text-sm">{error}</p>
          <button
            onClick={fetchArticles}
            className="px-6 py-3 bg-orange-500 text-white font-medium rounded-xl hover:bg-orange-600 transition-colors shadow-lg shadow-orange-500/20"
          >
            Try Again
          </button>
        </div>
      </div>
    )
  }

  const displayArticles = activeTab === 'saved' ? savedArticles : articles

  // Show admin page if toggled
  if (showAdmin) {
    return <AdminPage onBack={() => {
      setShowAdmin(false)
      fetchArticles()
    }} />
  }

  // Show discovery agent if toggled
  if (showAgent) {
    return <DiscoverAgent 
      onBack={() => {
        setShowAgent(false)
        fetchArticles()
      }}
      onArticlesAdded={() => {
        fetchArticles()
        showToast('Articles added!')
      }}
    />
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Toast Notification */}
      {toast && (
        <div className={`fixed top-4 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-full shadow-lg text-sm font-medium animate-fade-in ${
          toast.type === 'success' ? 'bg-gray-900 text-white' :
          toast.type === 'error' ? 'bg-red-500 text-white' :
          'bg-white text-gray-900 border border-gray-200'
        }`}>
          {toast.message}
        </div>
      )}

      {/* Pull to Refresh Indicator */}
      {isPulling && (
        <div 
          className="fixed top-0 left-0 right-0 flex justify-center z-40 transition-transform"
          style={{ transform: `translateY(${Math.min(pullDistance - 40, 30)}px)` }}
        >
          <div className={`w-10 h-10 bg-white rounded-full shadow-lg flex items-center justify-center transition-transform ${
            pullDistance > 80 ? 'scale-110' : ''
          }`}>
            <svg 
              className={`w-5 h-5 text-orange-500 transition-transform ${pullDistance > 80 ? 'rotate-180' : ''}`} 
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-3 sm:px-4 py-3 sm:py-4">
          <div className="flex items-center justify-between">
            {/* Logo - clickable */}
            <a href="/" className="flex items-center gap-2 group">
              <div className="w-9 h-9 sm:w-10 sm:h-10 bg-gradient-to-br from-orange-400 to-orange-500 rounded-xl flex items-center justify-center shadow-lg shadow-orange-500/20 group-hover:scale-105 transition-transform">
                <span className="text-xl sm:text-2xl">🐰</span>
              </div>
              <span className="text-lg sm:text-xl font-bold text-gray-900 hidden xs:inline">ReadRabbit</span>
            </a>

            {/* View Toggle + Actions */}
            <div className="flex items-center gap-1 sm:gap-2">
              <ViewToggle />
              <button
                onClick={() => setShowAgent(true)}
                className="p-2 sm:p-2.5 text-gray-500 hover:text-orange-600 hover:bg-orange-50 rounded-xl transition-colors"
                title="Discover"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </button>
              <button
                onClick={() => setShowAdmin(true)}
                className="p-2 sm:p-2.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-xl transition-colors"
                title="Admin"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="bg-white border-b border-gray-100 sticky top-[57px] sm:top-[65px] z-20">
        <div className="max-w-6xl mx-auto px-3 sm:px-4 py-2 sm:py-3">
          <div className="flex justify-center">
            <div className="inline-flex bg-gray-100 rounded-full p-1">
              <button
                onClick={() => setActiveTab('discover')}
                className={`px-4 sm:px-6 py-1.5 sm:py-2 rounded-full text-sm font-medium transition-all duration-200 ${
                  activeTab === 'discover'
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Discover
              </button>
              <button
                onClick={() => setActiveTab('saved')}
                className={`px-4 sm:px-6 py-1.5 sm:py-2 rounded-full text-sm font-medium transition-all duration-200 flex items-center gap-1.5 ${
                  activeTab === 'saved'
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Saved
                {savedArticles.length > 0 && (
                  <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                    activeTab === 'saved' ? 'bg-orange-100 text-orange-600' : 'bg-gray-200 text-gray-600'
                  }`}>
                    {savedArticles.length}
                  </span>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main 
        ref={mainRef}
        className="max-w-6xl mx-auto px-3 sm:px-4 py-4 sm:py-8"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Value Prop - shown on Discover tab */}
        {activeTab === 'discover' && articles.length > 0 && (
          <div className="text-center mb-6 sm:mb-8">
            <h1 className="text-lg sm:text-2xl font-bold text-gray-900 mb-1 sm:mb-2">
              Stop scrolling. Start reading.
            </h1>
            <p className="text-sm sm:text-base text-gray-500 max-w-md mx-auto">
              Curated long-form articles worth your time. Save what interests you, skip what doesn't.
            </p>
          </div>
        )}

        {activeTab === 'saved' && savedArticles.length === 0 ? (
          <div className="text-center py-12 sm:py-16 px-4">
            <div className="relative inline-block mb-6">
              <div className="w-24 h-24 bg-gradient-to-br from-orange-100 to-orange-50 rounded-3xl flex items-center justify-center mx-auto shadow-lg shadow-orange-500/10">
                <span className="text-5xl">📚</span>
              </div>
              <div className="absolute -bottom-1 -right-1 w-8 h-8 bg-gray-100 rounded-full flex items-center justify-center border-2 border-white">
                <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                </svg>
              </div>
            </div>
            <h3 className="text-xl font-bold text-gray-900 mb-2">Your reading list is empty</h3>
            <p className="text-gray-500 mb-2 text-sm max-w-xs mx-auto">
              Save articles you want to read later by tapping the bookmark icon
            </p>
            <p className="text-xs text-gray-400 mb-6">
              Or swipe right on articles in Single view
            </p>
            <button
              onClick={() => setActiveTab('discover')}
              className="px-6 py-3 bg-orange-500 text-white font-medium rounded-xl hover:bg-orange-600 transition-all shadow-lg shadow-orange-500/20 active:scale-95"
            >
              Start Discovering
            </button>
          </div>
        ) : viewMode === 'single' ? (
          /* Single View */
          <div className="py-2 sm:py-4">
            {displayArticles.length > 0 && (
              <ArticleCard
                article={activeTab === 'saved' ? displayArticles[singleIndex % displayArticles.length] : displayArticles[0]}
                onDismiss={handleDismiss}
                onSave={handleSave}
                isSaved={isArticleSaved(activeTab === 'saved' ? displayArticles[singleIndex % displayArticles.length]?.id : displayArticles[0]?.id)}
                viewMode="single"
              />
            )}
          </div>
        ) : (
          /* Feed View - single column vertical stack */
          <div className="max-w-2xl mx-auto space-y-4">
            {displayArticles.map((article, index) => (
              <div 
                key={article.id}
                className="animate-fade-in"
                style={{ animationDelay: `${(index % 4) * 50}ms` }}
              >
                <ArticleCard
                  article={article}
                  onDismiss={handleDismiss}
                  onSave={handleSave}
                  isSaved={isArticleSaved(article.id)}
                  viewMode="cards"
                />
              </div>
            ))}
          </div>
        )}

        {/* Show More Button - only on Discover tab, Feed view */}
        {activeTab === 'discover' && viewMode === 'feed' && (
          <div className="flex justify-center mt-8 sm:mt-10">
            <button
              onClick={handleShowMore}
              disabled={shuffling}
              className="group px-6 py-3 bg-white border border-gray-200 text-gray-700 font-medium rounded-xl hover:border-orange-300 hover:text-orange-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm hover:shadow-md flex items-center gap-2"
            >
              {shuffling ? (
                <>
                  <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Loading...</span>
                </>
              ) : (
                <>
                  <span>Show me more</span>
                  <svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                </>
              )}
            </button>
          </div>
        )}
      </main>

      {/* Bottom safe area for mobile */}
      <div className="h-6 sm:h-0"></div>
    </div>
  )
}

export default App
