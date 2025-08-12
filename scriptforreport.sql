SELECT category,
	SUM(CASE 
			WHEN amount > 0 then amount
			ELSE 0
			END) as total_spending
FROM transaction
GROUP BY category;

SELECT
  category,
  COALESCE(SUM(amount) FILTER (WHERE type_ofspending = 'liability'), 0) AS liability_total,
  COALESCE(SUM(amount) FILTER (WHERE type_ofspending = 'asset'), 0)     AS asset_total
FROM transaction
GROUP BY category
ORDER BY category;