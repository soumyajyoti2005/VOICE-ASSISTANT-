import asyncio
import random
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from backend.config import config


@dataclass
class RestaurantResult:
    name: str
    cuisine: str
    price_range: str
    rating: float
    address: str
    dietary_options: List[str]
    distance: str


MOCK_RESTAURANTS = [
    RestaurantResult(
        name="Green Garden Bistro",
        cuisine="Vegetarian",
        price_range="$15-25",
        rating=4.5,
        address="123 Main St, Downtown",
        dietary_options=["vegetarian", "vegan", "gluten-free"],
        distance="0.3 mi",
    ),
    RestaurantResult(
        name="Spice Route",
        cuisine="Indian",
        price_range="$20-35",
        rating=4.3,
        address="456 Oak Ave, Midtown",
        dietary_options=["vegetarian", "vegan"],
        distance="0.8 mi",
    ),
    RestaurantResult(
        name="Ocean Fresh",
        cuisine="Seafood",
        price_range="$30-50",
        rating=4.6,
        address="789 Harbor Blvd, Waterfront",
        dietary_options=["pescatarian"],
        distance="1.2 mi",
    ),
    RestaurantResult(
        name="Burger Joint",
        cuisine="American",
        price_range="$10-20",
        rating=4.1,
        address="321 Elm St, Westside",
        dietary_options=[],
        distance="0.5 mi",
    ),
    RestaurantResult(
        name="Mediterranean Delight",
        cuisine="Mediterranean",
        price_range="$18-30",
        rating=4.4,
        address="654 Pine Rd, Eastside",
        dietary_options=["vegetarian", "vegan", "gluten-free"],
        distance="0.7 mi",
    ),
    RestaurantResult(
        name="Sushi Zen",
        cuisine="Japanese",
        price_range="$25-45",
        rating=4.7,
        address="987 Cedar Ln, Downtown",
        dietary_options=["pescatarian", "gluten-free"],
        distance="1.0 mi",
    ),
]


async def search_restaurants(
    query: str,
    cuisine: Optional[str] = None,
    price_max: Optional[float] = None,
    dietary: Optional[str] = None,
    response_id: int = 0,
) -> List[Dict[str, Any]]:
    await asyncio.sleep(4)

    results = MOCK_RESTAURANTS.copy()

    if cuisine:
        results = [r for r in results if cuisine.lower() in r.cuisine.lower()]

    if dietary:
        results = [r for r in results if dietary.lower() in [d.lower() for d in r.dietary_options]]

    if price_max:
        filtered = []
        for r in results:
            price_str = r.price_range.replace("$", "")
            try:
                if "-" in price_str:
                    max_price = int(price_str.split("-")[1])
                else:
                    max_price = int(price_str)
                if max_price <= price_max:
                    filtered.append(r)
            except ValueError:
                pass
        results = filtered

    if not results:
        return [{"message": "No restaurants found matching your criteria"}]

    return [
        {
            "name": r.name,
            "cuisine": r.cuisine,
            "price_range": r.price_range,
            "rating": r.rating,
            "address": r.address,
            "dietary_options": r.dietary_options,
            "distance": r.distance,
        }
        for r in results[:5]
    ]