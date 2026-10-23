// Counts in words, said one way everywhere: "1 row", "1,204 rows". The noun
// agrees with the number (an inline helper once wrote "1 columns").

/** The noun for *n*: `plural(1, 'row')` is "row", `plural(2, 'query', 'queries')` is "queries". */
export const plural = (n, one, many = `${one}s`) => (Number(n) === 1 ? one : many)

/** *n* and its noun, with separators: "1 row", "1,204 rows". */
export const count = (n, one, many) => `${Number(n).toLocaleString('en-US')} ${plural(n, one, many)}`
