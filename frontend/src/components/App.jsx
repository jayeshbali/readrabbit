import React, { useState, useEffect, useCallback } from 'react'
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
  
  // UI State
  const [activeTab, setActiveTab] = useState('discover') // 'discover' | 'saved'
  const [viewMode, setViewMode] = useState('cards') // 'single' | 'cards' | 'feed'
  const [singleIndex, setSingleIndex] = useState(0) // For single view navigation
  const [showAdmin, setShowAdmin] = useState(false) // Admin page toggle
  const [showAgent, setShowAgent] = useState(false) // Discovery agent toggle

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

  const fetchArticles = useCallback(async () => {
    try {
      setShuffling(true)
      const count = viewMode === 'single' ? 1 : viewMode === 'feed' ? 8 : 4
      const response = await fetch(`${API_BASE}/articles/random?count=${count}`)
      if (!response.ok) throw new Error('Failed to fetch articles')
      const data = await response.json()
      setArticles(data.articles)
      setSingleIndex(0)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
      setShuffling(false)
    }
  }, [viewMode])

  useEffect(() => {
    fetchArticles()
  }, [fetchArticles])

  const handleDismiss = async (articleId) => {
    try {
      await fetch(`${API_BASE}/articles/${articleId}/dismiss`, { method: 'POST' })
      
      if (viewMode === 'single') {
        // Fetch a new article to replace
        const response = await fetch(`${API_BASE}/articles/random?count=1`)
        const data = await response.json()
        if (data.articles.length > 0) {
          setArticles(data.articles)
        }
      } else {
        // Replace the dismissed article
        const response = await fetch(`${API_BASE}/articles/random?count=1`)
        const data = await response.json()
        if (data.articles.length > 0) {
          setArticles((prev) =>
            prev.map((a) => (a.id === articleId ? data.articles[0] : a))
          )
        }
      }
    } catch (err) {
      console.error('Failed to dismiss article:', err)
    }
  }

  const handleSave = (article) => {
    const isAlreadySaved = savedArticles.some((a) => a.id === article.id)
    if (isAlreadySaved) {
      setSavedArticles((prev) => prev.filter((a) => a.id !== article.id))
    } else {
      setSavedArticles((prev) => [...prev, article])
    }
  }

  const isArticleSaved = (articleId) => {
    return savedArticles.some((a) => a.id === articleId)
  }

  const handleShowMore = () => {
    if (viewMode === 'single' && singleIndex < articles.length - 1) {
      setSingleIndex((prev) => prev + 1)
    } else {
      fetchArticles()
    }
  }

  // View mode icons
  const ViewToggle = () => (
    <div className="flex items-center bg-gray-100 rounded-lg p-1">
      <button
        onClick={() => setViewMode('single')}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
          viewMode === 'single' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'
        }`}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h7" />
        </svg>
        Single
      </button>
      <button
        onClick={() => setViewMode('cards')}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
          viewMode === 'cards' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'
        }`}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
        </svg>
        Cards
      </button>
      <button
        onClick={() => setViewMode('feed')}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
          viewMode === 'feed' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'
        }`}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
        </svg>
        Feed
      </button>
    </div>
  )

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-gray-500">Loading your reading list...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <p className="text-red-500 mb-4">{error}</p>
          <button
            onClick={fetchArticles}
            className="px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800"
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
      fetchArticles() // Refresh articles when returning
    }} />
  }

  // Show discovery agent if toggled
  if (showAgent) {
    return <DiscoverAgent 
      onBack={() => {
        setShowAgent(false)
        fetchArticles() // Refresh articles when returning
      }}
      onArticlesAdded={fetchArticles}
    />
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            {/* Logo */}
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-orange-100 rounded-lg flex items-center justify-center">
                <span className="text-orange-600 font-bold text-lg">📖</span>
              </div>
              <span className="text-xl font-bold text-gray-900">ReadRabbit</span>
            </div>

            {/* View Toggle + Actions */}
            <div className="flex items-center gap-3">
              <ViewToggle />
              <button
                onClick={() => setShowAgent(true)}
                className="p-2 text-gray-500 hover:text-orange-600 hover:bg-orange-50 rounded-lg"
                title="Discovery Agent"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </button>
              <button
                onClick={() => setShowAdmin(true)}
                className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
                title="Admin"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="max-w-6xl mx-auto px-4 pt-6">
        <div className="flex justify-center">
          <div className="inline-flex bg-gray-100 rounded-full p-1">
            <button
              onClick={() => setActiveTab('discover')}
              className={`px-6 py-2 rounded-full text-sm font-medium transition-colors ${
                activeTab === 'discover'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Discover
            </button>
            <button
              onClick={() => setActiveTab('saved')}
              className={`px-6 py-2 rounded-full text-sm font-medium transition-colors ${
                activeTab === 'saved'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Saved ({savedArticles.length})
            </button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {activeTab === 'saved' && savedArticles.length === 0 ? (
          <div className="text-center py-16">
            <div className="text-6xl mb-4">📚</div>
            <h3 className="text-lg font-medium text-gray-900 mb-2">No saved articles yet</h3>
            <p className="text-gray-500 mb-6">Save articles you want to read later</p>
            <button
              onClick={() => setActiveTab('discover')}
              className="px-5 py-2 bg-orange-500 text-white font-medium rounded-lg hover:bg-orange-600 transition-colors"
            >
              Discover Articles
            </button>
          </div>
        ) : viewMode === 'single' ? (
          /* Single View */
          <div className="py-4">
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
        ) : viewMode === 'feed' ? (
          /* Feed View */
          <div className="max-w-2xl mx-auto space-y-4">
            {displayArticles.map((article) => (
              <ArticleCard
                key={article.id}
                article={article}
                onDismiss={handleDismiss}
                onSave={handleSave}
                isSaved={isArticleSaved(article.id)}
                viewMode="cards"
              />
            ))}
          </div>
        ) : (
          /* Cards View (default) */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
            {displayArticles.map((article) => (
              <ArticleCard
                key={article.id}
                article={article}
                onDismiss={handleDismiss}
                onSave={handleSave}
                isSaved={isArticleSaved(article.id)}
                viewMode="cards"
              />
            ))}
          </div>
        )}

        {/* Show More Button - only on Discover tab */}
        {activeTab === 'discover' && (
          <div className="flex justify-center mt-10">
            <button
              onClick={handleShowMore}
              disabled={shuffling}
              className="px-6 py-3 text-gray-700 font-medium hover:text-gray-900 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {shuffling ? 'Loading...' : 'Show me more'}
            </button>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
