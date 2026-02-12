from flask import Blueprint, jsonify, render_template_string
from api.middleware import require_api_auth

docs_bp = Blueprint('docs', __name__)

REDOC_TEMPLATE = """
<!DOCTYPE html>
<html>
  <head>
    <title>BaileBelle API Reference</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>
      body { margin: 0; padding: 0; }
    </style>
  </head>
  <body>
    <div id="redoc-container"></div>
    <script src="https://cdn.jsdelivr.net/npm/redoc@2.0.0-rc.55/bundles/redoc.standalone.js"> </script>
    <script>
      Redoc.init('/api/v1/docs/swagger.json', {
        scrollYOffset: 50,
        hideDownloadButton: true,
        expandResponses: "200,201",
        theme: {
            colors: {
                primary: {
                    main: '#740c08'
                }
            },
            typography: {
                fontFamily: 'Roboto, sans-serif',
                headings: {
                    fontFamily: 'Montserrat, sans-serif'
                }
            }
        }
      }, document.getElementById('redoc-container'));
    </script>
  </body>
</html>
"""

@docs_bp.route('/', methods=['GET'])
def get_docs():
    return render_template_string(REDOC_TEMPLATE)

@docs_bp.route('/swagger.json', methods=['GET'])
def get_swagger_json():
    """Return manually curated OpenAPI 3.0 Spec"""
    return jsonify({
        "openapi": "3.0.0",
        "info": {
            "title": "BaileBelle API",
            "version": "1.0.0",
            "description": """
# Introduction
Welcome to the BaileBelle REST API. This API allows you to access products, manage orders, and process payments securely.

## Authentication
This API uses API Keys for authentication. You must provide the following headers with every request:

*   `X-API-Key`: Your public identifier.
*   `X-API-Secret`: Your secret key (do not share this client-side if possible, or use a proxy).

## Base URL
`http://localhost:8090/api/v1` (or your development host)
            """,
            "contact": {
                "name": "API Support",
                "email": "support@bailebelle.com"
            }
        },
        "servers": [
            {"url": "/api/v1", "description": "Current Server"}
        ],
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key"
                },
                "ApiSecretAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Secret"
                }
            },
            "schemas": {
                "Product": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "title": {"type": "string"},
                        "slug": {"type": "string"},
                        "price": {"type": "number"},
                        "sale_price": {"type": "number", "nullable": True},
                        "image": {"type": "string", "format": "uri"},
                        "stock_status": {"type": "string", "enum": ["instock", "outofstock"]},
                        "categories": {
                            "type": "array",
                            "items": {"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"}}}
                        }
                    }
                },
                "OrderInput": {
                    "type": "object",
                    "required": ["customer_email", "payment_method", "items"],
                    "properties": {
                        "customer_email": {"type": "string", "format": "email"},
                        "payment_method": {"type": "string", "enum": ["stripe", "paypal", "cod"]},
                        "billing": {"$ref": "#/components/schemas/Address"},
                        "shipping": {"$ref": "#/components/schemas/Address"},
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["product_id", "quantity"],
                                "properties": {
                                    "product_id": {"type": "integer"},
                                    "variation_id": {"type": "integer", "nullable": True},
                                    "quantity": {"type": "integer", "minimum": 1}
                                }
                            }
                        }
                    }
                },
                "Address": {
                    "type": "object",
                    "properties": {
                        "first_name": {"type": "string"},
                        "last_name": {"type": "string"},
                        "address": {"type": "string"},
                        "city": {"type": "string"},
                        "state": {"type": "string"},
                        "zipCode": {"type": "string"},
                        "country": {"type": "string"},
                        "phone": {"type": "string"}
                    }
                },
                "PaymentIntentResponse": {
                    "type": "object",
                    "properties": {
                        "client_secret": {"type": "string"},
                        "id": {"type": "string"}
                    }
                }
            }
        },
        "security": [
            {
                "ApiKeyAuth": [],
                "ApiSecretAuth": []
            }
        ],
        "tags": [
            {"name": "Products", "description": "Browse and search products"},
            {"name": "Orders", "description": "Manage orders"},
            {"name": "Payment", "description": "Process payments"},
            {"name": "Shipping", "description": "Shipping Methods"},
            {"name": "Tax", "description": "Tax Calculations"}
        ],
        "paths": {
            "/products/home": {
                "get": {
                    "tags": ["Products"],
                    "summary": "Get Home Page Data",
                    "description": "Returns configured sections for the homepage (New Arrivals, Categories, etc).",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "success": True,
                                        "data": {
                                            "sections": [
                                                {
                                                    "id": "section_1",
                                                    "title": "New Arrivals",
                                                    "type": "new_arrivals",
                                                    "products": [{"id": 1, "title": "Red Dress", "price": 99.00}]
                                                }
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/products/detail": {
                "get": {
                    "tags": ["Products"],
                    "summary": "Get Product Detail",
                    "parameters": [
                        {"name": "id", "in": "query", "schema": {"type": "integer"}},
                        {"name": "slug", "in": "query", "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {
                            "description": "Product Found",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Product"}
                                }
                            }
                        },
                        "404": {"description": "Not Found"}
                    }
                }
            },
            "/products/collections": {
                "get": {
                    "tags": ["Products"],
                    "summary": "List Products",
                    "parameters": [
                        {"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}},
                        {"name": "per_page", "in": "query", "schema": {"type": "integer", "default": 12}},
                        {"name": "search", "in": "query", "schema": {"type": "string"}},
                        {"name": "category_id", "in": "query", "schema": {"type": "integer"}},
                        {"name": "min_price", "in": "query", "schema": {"type": "number"}},
                        {"name": "max_price", "in": "query", "schema": {"type": "number"}},
                        {"name": "sort", "in": "query", "schema": {"type": "string", "enum": ["date", "price_asc", "price_desc", "name"]}}
                    ],
                    "responses": {
                        "200": {"description": "List of products"}
                    }
                }
            },
            "/shipping/zones": {
                "get": {
                    "tags": ["Shipping"],
                    "summary": "List All Shipping Zones",
                    "description": "Returns all configured shipping zones with their locations and methods.",
                    "responses": {
                        "200": {
                            "description": "List of shipping zones",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "success": True,
                                        "data": [
                                            {
                                                "id": 1,
                                                "name": "United States",
                                                "zone_order": 0,
                                                "locations": [
                                                    {"code": "US", "type": "country"}
                                                ],
                                                "methods": [
                                                    {
                                                        "id": 1,
                                                        "title": "Flat Rate Shipping",
                                                        "method_id": "flat_rate",
                                                        "cost": 10.00,
                                                        "enabled": True,
                                                        "tax_status": "taxable",
                                                        "order": 0
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    }
                },
                "post": {
                    "tags": ["Shipping"],
                    "summary": "Create Shipping Zone",
                    "description": "Create a new shipping zone.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["name"],
                                    "properties": {
                                        "name": {"type": "string", "example": "Europe"},
                                        "zone_order": {"type": "integer", "default": 0, "example": 1}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Zone created",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "success": True,
                                        "data": {
                                            "id": 2,
                                            "name": "Europe",
                                            "zone_order": 1,
                                            "locations": [],
                                            "methods": []
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/shipping/zones/{zone_id}": {
                "get": {
                    "tags": ["Shipping"],
                    "summary": "Get Shipping Zone",
                    "parameters": [
                        {"name": "zone_id", "in": "path", "required": True, "schema": {"type": "integer"}}
                    ],
                    "responses": {
                        "200": {"description": "Zone details"},
                        "404": {"description": "Zone not found"}
                    }
                },
                "put": {
                    "tags": ["Shipping"],
                    "summary": "Update Shipping Zone",
                    "parameters": [
                        {"name": "zone_id", "in": "path", "required": True, "schema": {"type": "integer"}}
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "zone_order": {"type": "integer"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {"description": "Zone updated"},
                        "404": {"description": "Zone not found"}
                    }
                },
                "delete": {
                    "tags": ["Shipping"],
                    "summary": "Delete Shipping Zone",
                    "parameters": [
                        {"name": "zone_id", "in": "path", "required": True, "schema": {"type": "integer"}}
                    ],
                    "responses": {
                        "200": {"description": "Zone deleted"},
                        "404": {"description": "Zone not found"}
                    }
                }
            },
            "/shipping/zones/{zone_id}/locations": {
                "post": {
                    "tags": ["Shipping"],
                    "summary": "Update Zone Locations",
                    "description": "Replace all locations for a zone.",
                    "parameters": [
                        {"name": "zone_id", "in": "path", "required": True, "schema": {"type": "integer"}}
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "locations": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "code": {"type": "string", "example": "US"},
                                                    "type": {"type": "string", "enum": ["country", "state"], "example": "country"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {"description": "Locations updated"}
                    }
                }
            },
            "/shipping/zones/{zone_id}/methods": {
                "post": {
                    "tags": ["Shipping"],
                    "summary": "Add Shipping Method",
                    "description": "Add a shipping method to a zone.",
                    "parameters": [
                        {"name": "zone_id", "in": "path", "required": True, "schema": {"type": "integer"}}
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["title", "method_id"],
                                    "properties": {
                                        "title": {"type": "string", "example": "Standard Shipping"},
                                        "method_id": {"type": "string", "enum": ["flat_rate", "free_shipping", "local_pickup"], "example": "flat_rate"},
                                        "cost": {"type": "number", "default": 0, "example": 10.00},
                                        "enabled": {"type": "boolean", "default": True},
                                        "tax_status": {"type": "string", "enum": ["taxable", "none"], "default": "taxable"},
                                        "description": {"type": "string", "nullable": True},
                                        "requirements": {"type": "string", "nullable": True},
                                        "min_order_amount": {"type": "number", "nullable": True, "example": 50.00},
                                        "order": {"type": "integer", "default": 0}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {"description": "Method created"}
                    }
                }
            },
            "/shipping/methods/{method_id}": {
                "put": {
                    "tags": ["Shipping"],
                    "summary": "Update Shipping Method",
                    "parameters": [
                        {"name": "method_id", "in": "path", "required": True, "schema": {"type": "integer"}}
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "method_id": {"type": "string"},
                                        "cost": {"type": "number"},
                                        "enabled": {"type": "boolean"},
                                        "tax_status": {"type": "string"},
                                        "min_order_amount": {"type": "number"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {"description": "Method updated"},
                        "404": {"description": "Method not found"}
                    }
                },
                "delete": {
                    "tags": ["Shipping"],
                    "summary": "Delete Shipping Method",
                    "parameters": [
                        {"name": "method_id", "in": "path", "required": True, "schema": {"type": "integer"}}
                    ],
                    "responses": {
                        "200": {"description": "Method deleted"},
                        "404": {"description": "Method not found"}
                    }
                }
            },
            "/shipping/calculate": {
                "post": {
                    "tags": ["Shipping"],
                    "summary": "Calculate Shipping Cost",
                    "description": "Calculate available shipping methods and costs for a location.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["country"],
                                    "properties": {
                                        "country": {"type": "string", "example": "US"},
                                        "state": {"type": "string", "example": "CA"},
                                        "cart_total": {"type": "number", "example": 100.00}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Available shipping methods",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "success": True,
                                        "data": {
                                            "methods": [
                                                {
                                                    "id": 1,
                                                    "title": "Flat Rate Shipping",
                                                    "cost": 10.00,
                                                    "method_id": "flat_rate"
                                                }
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/tax/settings": {
                "get": {
                    "tags": ["Tax"],
                    "summary": "Get Tax Settings",
                    "responses": {
                        "200": {"description": "Global tax settings"}
                    }
                }
            },
            "/tax/calculate": {
                "post": {
                    "tags": ["Tax"],
                    "summary": "Calculate Tax",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "subtotal": {"type": "number"},
                                        "shipping_cost": {"type": "number"},
                                        "country": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Calculated Tax",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "success": True,
                                        "data": {
                                            "amount": 15.00,
                                            "rate": 10.0,
                                            "label": "Tax"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/orders/": {
                "post": {
                    "tags": ["Orders"],
                    "summary": "Create Order",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OrderInput"}
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Order Created",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "success": True,
                                        "data": {
                                            "order_number": "ORD-20240101-ABC",
                                            "id": 123,
                                            "total": 150.00
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/orders/track/{number}": {
                "get": {
                    "tags": ["Orders"],
                    "summary": "Track Order",
                    "parameters": [
                        {"name": "number", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {"description": "Order Details"}
                    }
                }
            },
            "/payment/gateways": {
                "get": {
                    "tags": ["Payment"],
                    "summary": "Get Payment Gateways",
                    "responses": {
                        "200": {
                            "description": "List of available gateways",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "success": True,
                                        "data": [
                                            {"id": "stripe", "name": "Stripe", "publishable_key": "pk_test_..."}
                                        ]
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/payment/stripe/intent": {
                "post": {
                    "tags": ["Payment"],
                    "summary": "Create Stripe Payment Intent",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["amount", "order_id"],
                                    "properties": {
                                        "amount": {"type": "number"},
                                        "order_id": {"type": "integer"},
                                        "currency": {"type": "string", "default": "usd"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Intent Created",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/PaymentIntentResponse"}
                                }
                            }
                        }
                    }
                }
            }
        }
    })
