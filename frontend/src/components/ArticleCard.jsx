import React from 'react'

function ArticleCard({ article, onDismiss }) {
  const { title, url, source, author, read_time, topics, summary } = article

  return (
    <div className="article-card bg-white rounded-xl shadow-sm border border-gray-100 p-6 flex flex-col h-full">
      {/* Topics */}
      <div className="flex flex-wrap gap-2 mb-3">
        {topics.slice(0, 3).map((topic) => (
          <span
            key={topic}
            className="px-2 py-1 text-xs font-medium text-gray-600 bg-gray-100 rounded-full"
          >
            {topic}
          </span>
        ))}
      </div>

      {/* Title */}
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="group"
      >
        <h2 className="text-lg font-semibold text-gray-900 group-hover:text-blue-600 transition-colors mb-2 line-clamp-2">
          {title}
        </h2>
      </a>

      {/* Summary */}
      <p className="text-sm text-gray-600 mb-4 line-clamp-3 flex-grow">
        {summary}
      </p>

      {/* Meta */}
      <div className="flex items-center justify-between text-sm text-gray-500 mt-auto pt-4 border-t border-gray-100">
        <div className="flex items-center gap-2">
          <span className="font-medium text-gray-700">{source}</span>
          {author && author !== source && (
            <>
              <span>·</span>
              <span>{author}</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-1">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{read_time} min</span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2 mt-4">
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 text-center py-2 px-4 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 transition-colors"
        >
          Read
        </a>
        <button
          onClick={() => onDismiss(article.id)}
          className="py-2 px-3 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          title="Don't show again"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  )
}

export default ArticleCard
